import hashlib
import json
from uuid import uuid4

from pydantic import Field

from app.simulation.models.domain import Agent, Model, Resource, WorldState


class WorldEvent(Model):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    sequence_number: int
    tick: int
    event_type: str
    actor_id: str | None = None
    payload: dict
    schema_version: int = 1


def state_hash(world: WorldState) -> str:
    return hashlib.sha256(
        json.dumps(world.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def reduce_event(world: WorldState | None, event: WorldEvent) -> WorldState:
    if event.schema_version != 1:
        raise ValueError("Unsupported event schema")
    if event.event_type == "WORLD_CREATED":
        return WorldState.model_validate(event.payload["state"])
    if world is None:
        raise ValueError("Replay must begin with WORLD_CREATED")
    if event.event_type == "AGENT_UPDATED":
        agent = Agent.model_validate(event.payload["agent"])
        world.agents[agent.id] = agent
    elif event.event_type == "RESOURCE_UPDATED":
        resource = Resource.model_validate(event.payload["resource"])
        world.resources[resource.id] = resource
    elif event.event_type == "COMMAND_ACCEPTED":
        for field in ("status", "speed"):
            if field in event.payload:
                setattr(world, field, event.payload[field])
    elif event.event_type == "TICK_COMPLETED":
        world.tick = event.tick
        if state_hash(world) != event.payload["state_hash"]:
            raise ValueError(f"Replay hash mismatch at tick {world.tick}")
    return world
