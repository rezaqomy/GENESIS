from pydantic import Field

from app.simulation.chunks.access import WorldAccess
from app.simulation.models.domain import Agent, Model, Position, Resource, Tile, WorldState


class Observation(Model):
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
    local_effects: dict[str, float] = Field(default_factory=dict)


def build_observation(
    world: WorldState, actor_id: str, radius: int = 8, access: WorldAccess | None = None
) -> Observation:
    agent = world.agents[actor_id]
    access = access or WorldAccess(world)
    effects = {}
    if world.config.infinite:
        from app.simulation.settlements.effects import local_effects

        effects = local_effects(world, agent.position)
        radius = max(radius, int(effects["visibility"]))
    tiles, resources = access.visible(agent.position, radius)

    def visible(p: Position) -> bool:
        return agent.position.distance(p) <= radius

    from app.simulation.settlements.environment import conditions

    return Observation(
        environment=conditions(world.config.seed, world.tick),
        peers=[
            {"id": a.id, "name": a.name, "position": a.position.model_dump()}
            for a in world.agents.values()
            if a.alive and a.id != actor_id and visible(a.position)
        ],
        seed=world.config.seed,
        path_budget=world.config.path_budget,
        settlement=world.settlements[agent.settlement_id].model_dump(mode="json")
        if agent.settlement_id in world.settlements
        else None,
        local_effects=effects,
        buildings=[
            b.model_dump(mode="json")
            for b in world.buildings.values()
            if b.position.distance(agent.position) <= radius
            or (agent.settlement_id is not None and b.settlement_id == agent.settlement_id)
        ],
        tick=world.tick,
        self_agent=agent.model_copy(deep=True),
        tiles=[t.model_copy(deep=True) for t in tiles if visible(t.position)],
        resources=[r.model_copy(deep=True) for r in resources if visible(r.position)],
        occupied=[
            a.position.model_copy()
            for a in world.agents.values()
            if a.alive and a.id != actor_id and visible(a.position)
        ],
    )
