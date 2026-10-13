import math

from app.simulation.models.domain import Position, WorldState
from app.simulation.settlements.environment import SpatialIndex, clamp, conditions

BUILD_COSTS = {
    "campfire": {"stone": 2, "wood": 2, "fuel": 1},
    "shelter": {"wood": 6, "fiber": 3},
    "storage": {"wood": 4},
    "workbench": {"wood": 4, "stone": 2},
    "farm": {"wood": 2, "seeds": 2, "water": 1},
    "wooden_wall": {"wood": 3},
    "stone_wall": {"stone": 5, "clay": 1},
    "watchtower": {"wood": 8, "stone": 3},
    "bridge": {"wood": 5},
    "road": {"stone": 1},
    "remote_camp": {"wood": 3, "fiber": 2},
}
TOOL_COSTS = {
    "axe": {"wood": 2, "stone": 1, "fiber": 1},
    "pickaxe": {"wood": 2, "stone": 2},
    "torch": {"wood": 1, "fuel": 1},
}


def local_effects(
    world: WorldState, position: Position, index: SpatialIndex | None = None
) -> dict[str, float]:
    env = conditions(world.config.seed, world.tick)
    warmth, comfort, protection, visibility = 0.0, 0.0, 0.0, 8.0
    for b in world.buildings.values():
        if b.progress < 100 or b.durability <= 0:
            continue
        distance = b.position.distance(position)
        if b.kind == "campfire" and b.fuel > 0 and distance <= 5:
            warmth = max(warmth, (1 - distance / 6) * 0.85)
            protection += 0.18 * (1 - distance / 6)
        if b.kind in ("shelter", "remote_camp") and distance <= 2:
            comfort = max(comfort, 0.85 if b.kind == "shelter" else 0.6)
            warmth = max(warmth, 0.7)
            protection += 0.25
        if b.kind in ("wooden_wall", "stone_wall") and distance <= 3:
            protection += 0.035 if b.kind == "wooden_wall" else 0.06
        if b.kind == "watchtower" and distance <= 10:
            visibility = 12
            protection += 0.16 * (1 - distance / 11)
    peers = [a for a in (index or SpatialIndex(world)).nearby(position, 5)]
    torch_bearers = [
        a
        for a in peers
        if a.inventory.tools.get("torch", 0) > 0 and a.position.distance(position) <= 3
    ]
    if torch_bearers:
        warmth = max(warmth, 0.2)
        protection += 0.12
    safety = clamp(
        0.42
        + min(0.2, max(0, len(peers) - 1) * 0.04)
        + min(0.4, protection)
        - env["cold"] * 0.3 * (1 - warmth)
    )
    return {
        "safety": safety,
        "comfort": clamp(comfort),
        "warmth": clamp(warmth),
        "visibility": visibility,
        "crowding": clamp(max(0, len(peers) - 4) / 8),
    }


def settlement_tick(world: WorldState, access) -> None:
    next_tick = world.tick + 1
    for b in world.buildings.values():
        if b.progress < 100 or b.durability <= 0:
            continue
        if b.kind == "campfire" and next_tick % 12 == 0:
            b.fuel = max(0, b.fuel - 1)
        if b.kind == "farm" and next_tick % 24 == 0:
            settlement = world.settlements.get(b.settlement_id)
            if (
                settlement
                and settlement.storage.water > 0
                and settlement.storage.total <= settlement.storage.capacity - 2
            ):
                settlement.storage.water -= 1
                settlement.storage.food += 2
                b.food += 2  # lifetime yield instrumentation
        if next_tick % 240 == 0 and b.kind not in ("road", "bridge"):
            settlement = world.settlements.get(b.settlement_id)
            if settlement and settlement.storage.wood > 0:
                settlement.storage.wood -= 1
                b.durability = min(100, b.durability + 5)
            else:
                b.durability = max(0, b.durability - 5)
    index = SpatialIndex(world)
    for s in world.settlements.values():
        members = [
            world.agents[m] for m in s.members if m in world.agents and world.agents[m].alive
        ]
        buildings = [
            world.buildings[k]
            for k in s.buildings
            if k in world.buildings
            and world.buildings[k].progress == 100
            and world.buildings[k].durability > 0
        ]
        s.food_reserves = s.storage.food
        s.storage.capacity = 80 + sum(b.kind == "storage" for b in buildings) * 80
        s.influence = round(6 + math.sqrt(len(buildings)) * 2 + s.social_cohesion * 3, 2)
        if members:
            s.social_cohesion = clamp(
                sum(a.psychology.social_satisfaction for a in members) / len(members)
            )
        s.safety = local_effects(world, s.center, index)["safety"]
        shelters = sum(b.kind in ("shelter", "remote_camp") for b in buildings)
        s.comfort = clamp(shelters * 2 / max(1, len(members)))
        _, resources = access.visible(s.center, 12)
        s.resource_availability = clamp(
            sum(r.quantity for r in resources if r.kind in ("food", "wood", "stone")) / 200
        )
        s.crowding = clamp(max(0, len(index.nearby(s.center, 5)) - 4) / 8)
        s.exploration_activity = sum(a.position.distance(s.center) > s.influence for a in members)
