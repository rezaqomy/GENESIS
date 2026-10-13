from app.simulation.models.domain import Agent, Model, Position, Resource, Tile, WorldState


class Observation(Model):
    seed: int
    tick: int
    self_agent: Agent
    tiles: list[Tile]
    resources: list[Resource]
    occupied: list[Position]


def build_observation(world: WorldState, actor_id: str, radius: int = 8) -> Observation:
    agent = world.agents[actor_id]

    def visible(p: Position) -> bool:
        return agent.position.distance(p) <= radius

    return Observation(
        seed=world.config.seed,
        tick=world.tick,
        self_agent=agent.model_copy(deep=True),
        tiles=[t.model_copy(deep=True) for t in world.tiles if visible(t.position)],
        resources=[
            r.model_copy(deep=True) for r in world.resources.values() if visible(r.position)
        ],
        occupied=[
            a.position.model_copy()
            for a in world.agents.values()
            if a.alive and a.id != actor_id and visible(a.position)
        ],
    )
