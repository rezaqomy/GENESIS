from time import perf_counter
from uuid import uuid4

from app.simulation.actions.resolver import advance_physiology, resolve_intent
from app.simulation.chunks.access import WorldAccess
from app.simulation.chunks.generator import chunk_coord, chunk_key
from app.simulation.engine.generation import generate_world
from app.simulation.events.reducer import WorldEvent, agent_state, authoritative_state, state_hash
from app.simulation.models.domain import Action, AgentIntent, WorldConfig
from app.simulation.persistence.sqlite import EventStore


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

    def reset(self, config: WorldConfig) -> list[WorldEvent]:
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
        self.store.append(events, self.world)
        return events

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

    def tick(self, intents: list[AgentIntent] | None = None) -> list[WorldEvent]:
        started = perf_counter()
        decision_started = started
        world = self.world
        next_tick = world.tick + 1
        before_alive = {a.id: a.alive for a in world.agents.values()}
        before_resources = {k: r.quantity for k, r in world.resources.items()}
        before_modifications = dict(world.resource_modifications)
        before_explored = list(world.explored_chunks)
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
                intents = [self.policy.decide(o) for o in observations]
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
            accepted, message = resolve_intent(world, intent, self.access)
            actor = world.agents.get(intent.actor_id)
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
        interval = world.config.regeneration_ticks
        if not world.config.infinite and interval and next_tick % interval == 0:
            for resource in world.resources.values():
                resource.quantity = min(resource.capacity, resource.quantity + 1)
        if world.config.infinite:
            from app.simulation.settlements.effects import settlement_tick

            settlement_tick(world, self.access)
            for s in world.settlements.values():
                events.append(
                    self.event(
                        "SETTLEMENT_UPDATED",
                        {"settlement": s.model_dump(mode="json")},
                        tick=next_tick,
                    )
                )
            for key, b in world.buildings.items():
                if before_buildings.get(key) != b.model_dump(mode="json"):
                    events.append(
                        self.event(
                            "BUILDING_UPDATED",
                            {"building": b.model_dump(mode="json")},
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
                events.append(
                    self.event(
                        "AGENT_DIED",
                        {
                            "message": f"{agent.name} died "
                            f"({'starvation' if agent.hunger >= 100 else 'exposure'})"
                        },
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
                    if m.quantity + next_tick // interval - m.tick // interval >= m.capacity
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
