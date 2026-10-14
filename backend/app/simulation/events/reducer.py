import hashlib
import json
from uuid import uuid4

from pydantic import Field

from app.simulation.models.domain import (
    Agent,
    Building,
    Model,
    Resource,
    ResourceModification,
    Settlement,
    Tile,
    WorldState,
)


class WorldEvent(Model):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    sequence_number: int
    tick: int
    event_type: str
    actor_id: str | None = None
    payload: dict
    schema_version: int = 1


def agent_state(agent: Agent) -> dict:
    data = agent.model_dump(mode="json")
    # Preserve absent optional memory fields in old recordings until they are assigned.
    # After-images must use this same representation so replay keeps field presence.
    for field in (
        "food_memory",
        "recent_positions",
        "known_resources",
        "memories",
        "habits",
        "cognition_source",
        "thought",
    ):
        if field not in agent.model_fields_set:
            data.pop(field, None)
    return data


def authoritative_state(world: WorldState) -> dict:
    data = world.model_dump(mode="json")
    if world.config.infinite:
        # Terrain/resources are projections of seed + version + sparse modifications.
        data["tiles"] = []
        data["resources"] = {}
        data["agents"] = {key: agent_state(agent) for key, agent in world.agents.items()}
    else:
        # Preserve canonical hashes for original Phase 1 logs even as models gain fields.
        config_keys = ("seed", "width", "height", "agent_count", "regeneration_ticks")
        agent_keys = (
            "id",
            "name",
            "age",
            "visual_color",
            "health",
            "hunger",
            "energy",
            "position",
            "inventory",
            "destination",
            "current_action",
            "alive",
        )
        data = {
            key: data[key]
            for key in ("config", "tick", "status", "speed", "tiles", "agents", "resources")
        }
        data["config"] = {key: data["config"][key] for key in config_keys}
        for key, agent in data["agents"].items():
            data["agents"][key] = {field: agent[field] for field in agent_keys}
            data["agents"][key]["inventory"] = {
                field: agent["inventory"][field] for field in ("food", "wood", "capacity")
            }
    return data


def state_hash(world: WorldState) -> str:
    return hashlib.sha256(
        json.dumps(authoritative_state(world), sort_keys=True, separators=(",", ":")).encode()
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
    elif event.event_type == "BUILDING_UPDATED":
        b = Building.model_validate(event.payload["building"])
        world.buildings[b.id] = b
    elif event.event_type == "SETTLEMENT_UPDATED":
        s = Settlement.model_validate(event.payload["settlement"])
        world.settlements[s.id] = s
    elif event.event_type == "RESOURCE_MODIFIED":
        world.resource_modifications[event.payload["resource_id"]] = (
            ResourceModification.model_validate(event.payload["modification"])
        )
    elif event.event_type == "RESOURCE_RESTORED":
        world.resource_modifications.pop(event.payload["resource_id"], None)
    elif event.event_type == "TERRAIN_MODIFIED":
        world.terrain_modifications[event.payload["key"]] = Tile.model_validate(
            event.payload["tile"]
        )
    elif event.event_type == "WORLD_METADATA":
        world.explored_chunks = event.payload["explored_chunks"]
    elif event.event_type == "COMMAND_ACCEPTED":
        for field in ("status", "speed"):
            if field in event.payload:
                setattr(world, field, event.payload[field])
    elif event.event_type == "TICK_COMPLETED":
        world.tick = event.tick
        if state_hash(world) != event.payload["state_hash"]:
            raise ValueError(f"Replay hash mismatch at tick {world.tick}")
    return world
