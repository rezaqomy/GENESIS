import math
import random
from collections import deque

from app.simulation.models.domain import (
    Agent,
    Position,
    Resource,
    Terrain,
    Tile,
    WorldConfig,
    WorldState,
)

NAMES = ["Ada", "Finn", "Mira", "Leo", "Nova", "Jude", "Iris", "Theo", "Luna", "Ezra"]
COLORS = [
    "#ee8c70",
    "#e7be61",
    "#9c8de7",
    "#64bca5",
    "#e18cb1",
    "#69a9d5",
    "#db9c5b",
    "#91b95f",
    "#be87d2",
    "#a0b8bc",
]


def generate_world(config: WorldConfig) -> WorldState:
    if config.infinite:
        from app.simulation.chunks.access import WorldAccess

        world = WorldState(config=config, tiles=[], agents={}, resources={})
        from app.simulation.models.domain import Building, Inventory, Settlement
        from app.simulation.policies.personality import personality_for

        access = WorldAccess(world)
        sites = [Position(x=x, y=y) for y in range(-2, 4) for x in range(-2, 4) if (x, y) != (0, 0)]
        for i, p in enumerate(sites[: config.agent_count]):
            key = f"agent-{i:02d}"
            world.agents[key] = Agent(
                id=key,
                name=NAMES[i % 10],
                age=18 + i * 3,
                visual_color=COLORS[i % 10],
                position=p,
                hunger=20 + i,
                energy=min(100, 85 + i),
                personality=personality_for(config.seed, i),
                settlement_id="settlement-0",
                inventory=Inventory(capacity=24),
            )
        world.settlements["settlement-0"] = Settlement(
            id="settlement-0",
            name="Hearthgrove",
            center=Position(x=0, y=0),
            members=list(world.agents),
            storage=Inventory(
                food=12, wood=14, stone=10, fiber=6, fuel=8, seeds=4, water=6, clay=2, capacity=80
            ),
            buildings=["building-0"],
        )
        world.buildings["building-0"] = Building(
            id="building-0",
            kind="campfire",
            position=Position(x=0, y=0),
            settlement_id="settlement-0",
            progress=100,
            fuel=12,
        )
        for a in world.agents.values():
            a.known_chunks = sorted(
                {
                    f"{x},{y}"
                    for x in range((a.position.x - 8) // 32, (a.position.x + 8) // 32 + 1)
                    for y in range((a.position.y - 8) // 32, (a.position.y + 8) // 32 + 1)
                }
            )
        world.explored_chunks = sorted({k for a in world.agents.values() for k in a.known_chunks})
        from app.simulation.settlements.effects import settlement_tick

        settlement_tick(world, access)
        for key in access.active_keys():
            access.cache.get(*map(int, key.split(",")))
        return world
    rng = random.Random(config.seed)
    tiles = []
    for y in range(config.height):
        for x in range(config.width):
            # A winding river, two wooded groves, and seeded mineral/soil patches.
            river = config.width * 0.72 + math.sin(y * 0.27 + config.seed % 7) * 2.2
            noise = rng.random()
            grove = (x - config.width * 0.22) ** 2 + (y - config.height * 0.3) ** 2 < 45 or (
                x - config.width * 0.5
            ) ** 2 + (y - config.height * 0.77) ** 2 < 35
            if abs(x - river) < 1.2 and y not in (config.height // 3, config.height * 2 // 3):
                terrain = Terrain.WATER
            elif noise < 0.035:
                terrain = Terrain.ROCK
            elif grove:
                terrain = Terrain.FOREST
            elif noise > 0.91:
                terrain = Terrain.SOIL
            else:
                terrain = Terrain.GRASS
            tiles.append(
                Tile(
                    position=Position(x=x, y=y),
                    terrain=terrain,
                    walkable=terrain not in (Terrain.WATER, Terrain.ROCK),
                )
            )
    # Place agents/resources in the largest walkable component, guaranteeing reachable food.
    walkable = {(t.position.x, t.position.y) for t in tiles if t.walkable}
    unseen = set(walkable)
    components = []
    while unseen:
        start = min(unseen)
        queue = deque([start])
        unseen.remove(start)
        component = []
        while queue:
            x, y = queue.popleft()
            component.append((x, y))
            for p in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
                if p in unseen:
                    unseen.remove(p)
                    queue.append(p)
        components.append(component)
    sites = sorted(max(components, key=len), key=lambda p: (p[1], p[0]))
    rng.shuffle(sites)
    agents = {}
    for i, (x, y) in enumerate(sites[: config.agent_count]):
        key = f"agent-{i:02d}"
        agents[key] = Agent(
            id=key,
            name=NAMES[i % 10] + (f" {i // 10 + 1}" if i >= 10 else ""),
            age=rng.randint(18, 48),
            visual_color=COLORS[i % 10],
            hunger=rng.randint(15, 45),
            energy=rng.randint(65, 100),
            position=Position(x=x, y=y),
        )
    resources = {}
    for i, (x, y) in enumerate(
        sites[config.agent_count : config.agent_count + max(35, len(sites) // 14)]
    ):
        kind = "wood" if i % 3 == 0 else "food"
        key = f"resource-{i:03d}"
        resources[key] = Resource(
            id=key,
            position=Position(x=x, y=y),
            kind=kind,
            quantity=8 if kind == "food" else 12,
            capacity=8 if kind == "food" else 12,
        )
    return WorldState(config=config, tiles=tiles, agents=agents, resources=resources)
