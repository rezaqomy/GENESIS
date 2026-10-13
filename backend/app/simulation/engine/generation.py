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
