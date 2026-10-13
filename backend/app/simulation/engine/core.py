from uuid import uuid4

from app.simulation.actions.resolver import advance_physiology, resolve_intent
from app.simulation.engine.generation import generate_world
from app.simulation.events.reducer import WorldEvent, state_hash
from app.simulation.models.domain import Action, AgentIntent, WorldConfig
from app.simulation.persistence.sqlite import EventStore


class Engine:
    """Synchronous authoritative core. The service calls it from one asyncio task only."""

    def __init__(self, config: WorldConfig, store: EventStore, policy=None, restore=False):
        self.store = store
        self.policy = policy
        self.sequence = 0
        latest = store.latest_run() if restore else None
        if latest:
            self.run_id = latest
            self.world = store.replay(latest, use_snapshot=True)
            self.sequence = store.sequence(latest)
            if self.world.status != "paused":
                self.command("pause")
        else:
            self.reset(config)

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
        events = [
            self.event(
                "WORLD_CREATED",
                {
                    "state": self.world.model_dump(mode="json"),
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
        world = self.world
        next_tick = world.tick + 1
        before_alive = {a.id: a.alive for a in world.agents.values()}
        before_resources = {k: r.quantity for k, r in world.resources.items()}
        advance_physiology(world)
        if intents is None:
            if self.policy:
                from app.simulation.observation.builder import build_observation

                # Freeze all observations before any action resolves.
                observations = [
                    build_observation(world, aid)
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
        events = []
        # One intent per actor. Stable lexicographic order breaks every contention.
        seen = set()
        for intent in sorted(intents, key=lambda i: i.actor_id):
            if intent.actor_id in seen:
                continue
            seen.add(intent.actor_id)
            accepted, message = resolve_intent(world, intent)
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
        if interval and next_tick % interval == 0:
            for resource in world.resources.values():
                resource.quantity = min(resource.capacity, resource.quantity + 1)
        for agent in world.agents.values():
            events.append(
                self.event(
                    "AGENT_UPDATED", {"agent": agent.model_dump(mode="json")}, agent.id, next_tick
                )
            )
            if before_alive[agent.id] and not agent.alive:
                events.append(
                    self.event(
                        "AGENT_DIED",
                        {"message": f"{agent.name} died of starvation"},
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
        world.tick = next_tick
        events.append(self.event("TICK_COMPLETED", {"state_hash": state_hash(world)}))
        self.store.append(events, world if next_tick % 25 == 0 else None)
        return events
