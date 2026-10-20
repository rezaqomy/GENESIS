from functools import wraps
from time import perf_counter
from uuid import uuid4

from app.simulation.actions.resolver import advance_physiology, resolve_intent, resolve_survival
from app.simulation.chunks.access import WorldAccess, recovered_quantity, regeneration_interval
from app.simulation.chunks.generator import chunk_coord, chunk_key
from app.simulation.engine.generation import generate_world
from app.simulation.events.reducer import (
    WorldEvent,
    agent_state,
    authoritative_state,
    building_state,
    settlement_state,
    state_hash,
)
from app.simulation.models.domain import Action, AgentIntent, WorldConfig
from app.simulation.persistence.sqlite import EventStore


def atomic_update(method):
    """Publish mutations only together with their durable log; rollback on any failure."""

    @wraps(method)
    def update(self, *args, **kwargs):
        if getattr(self, "_updating", False):
            return method(self, *args, **kwargs)
        previous_world = getattr(self, "world", None)
        backup = previous_world.model_copy(deep=True) if previous_world is not None else None
        previous_access = getattr(self, "access", None)
        previous_run = getattr(self, "run_id", None)
        previous_sequence, previous_metrics = self.sequence, dict(self.metrics)
        self._updating = True
        try:
            with self.store.transaction():
                return method(self, *args, **kwargs)
        except Exception:
            self.sequence, self.metrics = previous_sequence, previous_metrics
            if backup is not None:
                self.world, self.run_id = backup, previous_run
                self.access = WorldAccess(
                    backup, previous_access.cache if previous_access else None
                )
            # Inference may hold observations of the uncommitted tick.
            if hasattr(self.policy, "reset"):
                self.policy.reset(previous_run or "")
            raise
        finally:
            self._updating = False

    return update


class Engine:
    """Synchronous authoritative core. The service calls it from one asyncio task only."""

    def __init__(self, config: WorldConfig, store: EventStore, policy=None, restore=False):
        self.store = store
        self.policy = policy
        self.sequence = 0
        self.metrics = {"tick_duration_ms": 0.0, "decision_duration_ms": 0.0}
        latest = store.latest_run() if restore else None
        if latest:
            self.run_id = latest
            self.world = store.replay(latest, use_snapshot=True)
            self.sequence = store.sequence(latest)
            if self.world.status != "paused":
                self.command("pause")
        else:
            self.reset(config)
        self.access = WorldAccess(self.world)

    def event(
        self, event_type: str, payload: dict, actor_id: str | None = None, tick: int | None = None
    ) -> WorldEvent:
        self.sequence += 1
        return WorldEvent(
            run_id=self.run_id,
            sequence_number=self.sequence,
            tick=self.world.tick if tick is None else tick,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload,
        )

    @atomic_update
    def reset(self, config: WorldConfig, record_command: bool = False) -> list[WorldEvent]:
        self.run_id = str(uuid4())
        self.sequence = 0
        self.world = generate_world(config)
        self.access = WorldAccess(self.world)
        events = [
            self.event(
                "WORLD_CREATED",
                {
                    "state": authoritative_state(self.world),
                    "message": f"World created with seed {config.seed}",
                },
            )
        ]
        if record_command:
            events.append(
                self.event(
                    "COMMAND_ACCEPTED",
                    {"command": "reset", "seed": config.seed, "message": "Simulation: reset"},
                )
            )
        self.store.append(events, self.world)
        return events

    @atomic_update
    def command(self, command: str, value: float | None = None) -> list[WorldEvent]:
        payload = {"command": command, "message": f"Simulation: {command}"}
        if command in ("start", "resume"):
            self.world.status = "running"
            payload["status"] = "running"
        elif command == "pause":
            self.world.status = "paused"
            payload["status"] = "paused"
        elif command == "speed":
            if value not in (0.5, 1, 2, 4, 8):
                raise ValueError("Unsupported speed")
            self.world.speed = value
            payload["speed"] = value
        elif command == "step":
            if self.world.status != "paused":
                raise ValueError("Pause before stepping")
        else:
            raise ValueError("Unknown command")
        events = [self.event("COMMAND_ACCEPTED", payload)]
        self.store.append(events)
        if command == "step":
            events += self.tick()
        return events

    @atomic_update
    def tick(self, intents: list[AgentIntent] | None = None) -> list[WorldEvent]:
        started = perf_counter()
        decision_started = started
        world = self.world
        next_tick = world.tick + 1
        before_alive = {a.id: a.alive for a in world.agents.values()}
        before_resources = {k: r.quantity for k, r in world.resources.items()}
        before_modifications = dict(world.resource_modifications)
        before_explored = list(world.explored_chunks)
        before_ecosystem = world.ecosystem.model_dump(mode="json") if world.ecosystem else None
        before_buildings = {key: b.model_dump(mode="json") for key, b in world.buildings.items()}
        before_terrain = {
            key: t.model_dump(mode="json") for key, t in world.terrain_modifications.items()
        }
        advance_physiology(world)
        if world.config.infinite:
            from app.simulation.settlements.environment import experience_tick

            experience_tick(world, self.access)
        if intents is None:
            if self.policy:
                from app.simulation.observation.builder import build_observation

                # Freeze all observations before any action resolves.
                observations = [
                    build_observation(world, aid, access=self.access)
                    for aid in sorted(world.agents)
                    if world.agents[aid].alive
                ]
                intents = (
                    self.policy.decide_batch(observations)
                    if hasattr(self.policy, "decide_batch")
                    else [self.policy.decide(o) for o in observations]
                )
                if world.config.infinite:
                    from app.simulation.planning.navigation import coordinate_movements

                    intents = coordinate_movements(observations, intents, world.tick)
            else:
                intents = [
                    AgentIntent(actor_id=a.id, action=Action.IDLE)
                    for a in world.agents.values()
                    if a.alive
                ]
        self.metrics["decision_duration_ms"] = round((perf_counter() - decision_started) * 1000, 2)
        events = []
        # One intent per actor. Stable lexicographic order breaks every contention.
        seen = set()
        for intent in sorted(intents, key=lambda i: i.actor_id):
            if intent.actor_id in seen:
                continue
            seen.add(intent.actor_id)
            from app.simulation.cognition.tiers import action_snapshot

            before_action = action_snapshot(world.agents.get(intent.actor_id))
            actor = world.agents.get(intent.actor_id)
            if actor and actor.alive and intent.task is not None:
                actor.task = intent.task.model_copy(deep=True)
            accepted, message = resolve_intent(world, intent, self.access)
            actor = world.agents.get(intent.actor_id)
            if world.config.infinite:
                from app.simulation.community import record_work

                record_work(world, actor, intent, accepted)
            if actor and actor.alive and intent.decision is not None:
                previous_goal = actor.decision.selected_goal
                actor.decision = intent.decision.model_copy(deep=True)
                if accepted:
                    actor.decision.failures = 0
                    if intent.action == Action.MOVE and actor.decision.selected_goal == "explore":
                        actor.exploration_steps += 1
                else:
                    actor.decision.failures += 1
                    if actor.decision.failures >= 3:
                        actor.decision.commitment_until = 0
                        actor.decision.cooldowns[actor.decision.selected_goal] = next_tick + 8
                if previous_goal != actor.decision.selected_goal:
                    events.append(
                        self.event(
                            "GOAL_SELECTED",
                            {
                                "goal": actor.decision.selected_goal,
                                "message": f"{actor.name} chose "
                                + actor.decision.selected_goal.replace("_", " "),
                                "factors": actor.decision.factors,
                            },
                            actor.id,
                            next_tick,
                        )
                    )
            from app.simulation.cognition.memory import experience

            experience(
                world, actor, intent, accepted, message, next_tick, before_action, self.access
            )
            if world.config.infinite:
                from app.simulation.planning.tasks import update_task

                outcome = update_task(world, actor, intent, accepted, before_action, next_tick)
                if outcome:
                    events.append(
                        self.event(
                            "TASK_COMPLETED",
                            {
                                "outcome": outcome.model_dump(mode="json"),
                                "message": f"{actor.name}: {outcome.kind} {outcome.status}: "
                                f"{outcome.reason}",
                            },
                            actor.id,
                            next_tick,
                        )
                    )
                if intent.navigation_note:
                    events.append(
                        self.event(
                            "NAVIGATION_ADJUSTED",
                            {"message": intent.navigation_note},
                            intent.actor_id,
                            next_tick,
                        )
                    )
            if intent.observation_tick is not None:
                events.append(
                    self.event(
                        "COGNITION_CONSUMED",
                        {
                            "source": intent.cognition_source,
                            "observation_tick": intent.observation_tick,
                            "thought": intent.thought,
                            "intent": intent.model_dump(mode="json"),
                        },
                        intent.actor_id,
                        next_tick,
                    )
                )
            if accepted and intent.utterance:
                events.append(
                    self.event(
                        "DIALOGUE",
                        {
                            "peer_id": intent.peer_id,
                            "message": f"{actor.name} → "
                            f"{world.agents[intent.peer_id].name}: {intent.utterance}",
                        },
                        intent.actor_id,
                        next_tick,
                    )
                )
            if not accepted and intent.actor_id in world.agents:
                world.agents[intent.actor_id].current_action = Action.IDLE
            events.append(
                self.event(
                    "ACTION_RESOLVED" if accepted else "ACTION_REJECTED",
                    {
                        "action": intent.action,
                        "message": message,
                        "intent": intent.model_dump(mode="json"),
                    },
                    intent.actor_id,
                    next_tick,
                )
            )
        if world.config.infinite:
            resolve_survival(world)
            from app.simulation.ecology.environment import advance_ecology, release_dead
            from app.simulation.settlements.environment import conditions

            for event_type, payload in [
                *advance_ecology(
                    world, self.access, next_tick, conditions(world.config.seed, next_tick)
                ),
                *release_dead(world, next_tick),
            ]:
                events.append(self.event(event_type, payload, tick=next_tick))
            if before_ecosystem != world.ecosystem.model_dump(mode="json"):
                events.append(
                    self.event(
                        "ECOSYSTEM_UPDATED",
                        {"ecosystem": world.ecosystem.model_dump(mode="json")},
                        tick=next_tick,
                    )
                )
        interval = world.config.regeneration_ticks
        if not world.config.infinite and interval:
            for resource in world.resources.values():
                if next_tick % regeneration_interval(interval, resource.kind) == 0:
                    resource.quantity = min(resource.capacity, resource.quantity + 1)
        if world.config.infinite:
            from app.simulation.engineering.weathering import weather_damage
            from app.simulation.settlements.effects import settlement_tick
            from app.simulation.settlements.environment import conditions

            for event_type, payload in weather_damage(
                world, next_tick, conditions(world.config.seed, next_tick)
            ):
                events.append(self.event(event_type, payload, tick=next_tick))
            settlement_tick(world, self.access)
            from app.simulation.community import update_projects

            for event_type, payload in update_projects(world, next_tick):
                events.append(self.event(event_type, payload, tick=next_tick))
            for s in world.settlements.values():
                events.append(
                    self.event(
                        "SETTLEMENT_UPDATED",
                        {"settlement": settlement_state(s)},
                        tick=next_tick,
                    )
                )
            for key, b in world.buildings.items():
                if before_buildings.get(key) != b.model_dump(mode="json"):
                    events.append(
                        self.event(
                            "BUILDING_UPDATED",
                            {"building": building_state(b)},
                            tick=next_tick,
                        )
                    )
            for key, t in world.terrain_modifications.items():
                if before_terrain.get(key) != t.model_dump(mode="json"):
                    events.append(
                        self.event(
                            "TERRAIN_MODIFIED",
                            {"key": key, "tile": t.model_dump(mode="json")},
                            tick=next_tick,
                        )
                    )
        # A plan can fail through exposure before its owner gets an action this tick.
        if world.config.infinite:
            from app.simulation.planning.tasks import finish_task

            for agent in world.agents.values():
                if not agent.alive and agent.task and agent.task.status == "active":
                    outcome = finish_task(
                        agent, "failed", "Actor died before completing the task", next_tick
                    )
                    events.append(
                        self.event(
                            "TASK_COMPLETED",
                            {
                                "outcome": outcome.model_dump(mode="json"),
                                "message": f"{agent.name}: task failed after death",
                            },
                            agent.id,
                            next_tick,
                        )
                    )
        for agent in world.agents.values():
            events.append(
                self.event(
                    "AGENT_UPDATED",
                    {
                        "agent": agent_state(agent)
                        if world.config.infinite
                        else agent.model_dump(mode="json")
                    },
                    agent.id,
                    next_tick,
                )
            )
            if before_alive[agent.id] and not agent.alive:
                cause = (
                    agent.combat.death_cause
                    if agent.combat and agent.combat.death_cause
                    else "starvation"
                    if agent.hunger >= 100
                    else "exposure"
                )
                events.append(
                    self.event(
                        "AGENT_DIED",
                        {"message": f"{agent.name} died ({cause})"},
                        agent.id,
                        next_tick,
                    )
                )
        for key, resource in world.resources.items():
            if resource.quantity != before_resources[key]:
                events.append(
                    self.event(
                        "RESOURCE_UPDATED",
                        {"resource": resource.model_dump(mode="json")},
                        tick=next_tick,
                    )
                )
        if world.config.infinite:
            interval = world.config.regeneration_ticks
            if interval:
                restored = [
                    key
                    for key, m in world.resource_modifications.items()
                    if recovered_quantity(
                        m.quantity, m.capacity, m.tick, next_tick, interval, key.rsplit(":", 1)[-1]
                    )
                    >= m.capacity
                ]
                for key in restored:
                    del world.resource_modifications[key]
                    events.append(
                        self.event("RESOURCE_RESTORED", {"resource_id": key}, tick=next_tick)
                    )
            for resource_id, modification in world.resource_modifications.items():
                if before_modifications.get(resource_id) != modification:
                    events.append(
                        self.event(
                            "RESOURCE_MODIFIED",
                            {
                                "resource_id": resource_id,
                                "modification": modification.model_dump(mode="json"),
                            },
                            tick=next_tick,
                        )
                    )
            for a in world.agents.values():
                if a.alive:
                    key = chunk_key(*chunk_coord(a.position))
                    if key not in world.explored_chunks:
                        world.explored_chunks.append(key)
            world.explored_chunks = world.explored_chunks[-1024:]
            if before_explored != world.explored_chunks:
                events.append(
                    self.event(
                        "WORLD_METADATA", {"explored_chunks": world.explored_chunks}, tick=next_tick
                    )
                )
        world.tick = next_tick
        events.append(self.event("TICK_COMPLETED", {"state_hash": state_hash(world)}))
        self.store.append(events, world if next_tick % 25 == 0 else None)
        self.metrics["tick_duration_ms"] = round((perf_counter() - started) * 1000, 2)
        return events
