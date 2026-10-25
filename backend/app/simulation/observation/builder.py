from pydantic import Field

from app.simulation.chunks.access import WorldAccess
from app.simulation.models.domain import Agent, Model, Position, Resource, Tile, WorldState
from app.simulation.observation.vision import vision_radius


class Observation(Model):
    vision_radius: int = 8
    peers: list[dict] = Field(default_factory=list)
    environment: dict = Field(default_factory=dict)
    seed: int
    tick: int
    self_agent: Agent
    tiles: list[Tile]
    resources: list[Resource]
    occupied: list[Position]
    path_budget: int = 600
    settlement: dict | None = None
    buildings: list[dict] = Field(default_factory=list)
    animals: list[dict] = Field(default_factory=list)
    crops: list[dict] = Field(default_factory=list)
    drops: list[dict] = Field(default_factory=list)
    local_effects: dict[str, float] = Field(default_factory=dict)


def build_observation(
    world: WorldState, actor_id: str, radius: int | None = None, access: WorldAccess | None = None
) -> Observation:
    agent = world.agents[actor_id]
    access = access or WorldAccess(world)
    effects = {}
    if world.config.infinite:
        from app.simulation.settlements.effects import local_effects

        effects = local_effects(world, agent.position)
    effective_radius = vision_radius(agent, effects)
    # Callers may narrow perception for diagnostics, never expand an actor's sight.
    radius = effective_radius if radius is None else max(0, min(radius, effective_radius))
    tiles, resources = access.visible(agent.position, radius)

    def visible(p: Position) -> bool:
        return agent.position.distance(p) <= radius

    from app.simulation.settlements.environment import conditions

    settlement = world.settlements.get(agent.settlement_id)
    # Membership is not a live global feed. Inspect communal supplies only locally;
    # omit remote project lists, population, and aggregate resource/exploration metrics.
    settlement_view = None
    if settlement and agent.alive and visible(settlement.center):
        settlement_view = {
            "id": settlement.id,
            "name": settlement.name,
            "center": settlement.center.model_dump(),
            "storage": settlement.storage.model_dump(),
            "food_reserves": settlement.storage.food,
            "community": settlement.community.model_dump(mode="json")
            if settlement.community
            else None,
        }

    return Observation(
        vision_radius=radius,
        animals=[
            v.model_dump(mode="json")
            for v in world.ecosystem.animals.values()
            if agent.alive and visible(v.position)
        ]
        if world.ecosystem
        else [],
        crops=[
            v.model_dump(mode="json")
            for v in world.ecosystem.crops.values()
            if agent.alive and visible(v.position)
        ]
        if world.ecosystem
        else [],
        drops=[
            v.model_dump(mode="json")
            for v in world.ecosystem.drops.values()
            if agent.alive and visible(v.position)
        ]
        if world.ecosystem
        else [],
        environment=conditions(world.config.seed, world.tick),
        peers=[
            {
                "id": a.id,
                "name": a.name,
                "position": a.position.model_dump(),
                "need": "care"
                if a.health < 45 and a.inventory.food == 0
                else "food"
                if a.hunger >= 55 and a.inventory.food == 0
                else None,
                "trade_offer": a.workshop.offer.model_dump(mode="json")
                if a.workshop
                and a.workshop.offer
                and a.workshop.offer.peer_id == actor_id
                and agent.position.distance(a.position) <= 1
                else None,
                "tools": [
                    {"id": key, "design": trial.design.model_dump(mode="json")}
                    for key, trial in (a.inventions.designs.items() if a.inventions else [])
                    if a.inventory.tools.get(key, 0) > 0
                ]
                if agent.position.distance(a.position) <= 1
                else [],
            }
            for a in world.agents.values()
            if agent.alive and a.alive and a.id != actor_id and visible(a.position)
        ],
        seed=world.config.seed,
        path_budget=world.config.path_budget,
        settlement=settlement_view,
        local_effects=effects,
        buildings=[
            b.model_dump(mode="json")
            for b in world.buildings.values()
            if agent.alive and visible(b.position)
        ],
        tick=world.tick,
        self_agent=agent.model_copy(deep=True),
        tiles=[t.model_copy(deep=True) for t in tiles if agent.alive and visible(t.position)],
        resources=[
            r.model_copy(deep=True) for r in resources if agent.alive and visible(r.position)
        ],
        occupied=[
            a.position.model_copy()
            for a in world.agents.values()
            if agent.alive and a.alive and a.id != actor_id and visible(a.position)
        ],
    )
