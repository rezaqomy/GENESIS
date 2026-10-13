from collections import OrderedDict

from app.simulation.chunks.generator import SIZE, chunk_coord, chunk_key, generate_chunk
from app.simulation.models.domain import (
    Chunk,
    Position,
    Resource,
    ResourceModification,
    Tile,
    WorldState,
)


class ChunkCache:
    def __init__(self, seed: int, version: int, capacity: int = 64):
        self.seed, self.version, self.capacity = seed, version, capacity
        self.entries: OrderedDict[str, Chunk] = OrderedDict()
        self.generations = 0

    def get(self, cx: int, cy: int) -> Chunk:
        key = chunk_key(cx, cy)
        if key in self.entries:
            self.entries.move_to_end(key)
            return self.entries[key]
        chunk = generate_chunk(self.seed, cx, cy, self.version)
        self.generations += 1
        self.entries[key] = chunk
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
        return chunk


def quantity_at(world: WorldState, resource: Resource) -> int:
    change = world.resource_modifications.get(resource.id)
    if change is None:
        return resource.capacity
    interval = world.config.regeneration_ticks
    # Lazy catch-up counts global regeneration boundaries, independent of activation/camera.
    gains = world.tick // interval - change.tick // interval if interval else 0
    return min(resource.capacity, change.quantity + max(0, gains))


class WorldAccess:
    def __init__(self, world: WorldState, cache: ChunkCache | None = None):
        self.world = world
        self.structure_index = {}
        self.structure_count = -1
        self.cache = cache or ChunkCache(
            world.config.seed, world.config.generator_version, world.config.chunk_cache_size
        )

    def tile(self, p: Position) -> Tile | None:
        w = self.world
        if not w.config.infinite:
            if not (0 <= p.x < w.config.width and 0 <= p.y < w.config.height):
                return None
            return w.tiles[p.y * w.config.width + p.x]
        modified = w.terrain_modifications.get(f"{p.x},{p.y}")
        if modified:
            return self.building_tile(modified.model_copy(deep=True))
        chunk = self.cache.get(*chunk_coord(p))
        tile = chunk.tiles[(p.y % SIZE) * SIZE + p.x % SIZE].model_copy(deep=True)
        return self.building_tile(tile)

    def building_tile(self, tile: Tile) -> Tile:
        if self.structure_count != len(self.world.buildings):
            self.structure_index = {
                (b.position.x, b.position.y): b for b in self.world.buildings.values()
            }
            self.structure_count = len(self.world.buildings)
        b = self.structure_index.get((tile.position.x, tile.position.y))
        if b and b.progress == 100 and b.durability > 0:
            if b.kind in ("wooden_wall", "stone_wall", "watchtower"):
                tile.walkable = False
            elif b.kind in ("bridge", "road"):
                tile.walkable = True
        return tile

    def resource(self, resource_id: str) -> Resource | None:
        if not self.world.config.infinite:
            return self.world.resources.get(resource_id)
        try:
            _, x, y, _ = resource_id.split(":")
            chunk = self.cache.get(int(x) // SIZE, int(y) // SIZE)
        except (ValueError, TypeError):
            return None
        base = chunk.resources.get(resource_id)
        if base is None:
            return None
        result = base.model_copy(deep=True)
        result.quantity = quantity_at(self.world, base)
        return result

    def harvest(self, resource: Resource, amount: int = 1):
        if self.world.config.infinite:
            self.world.resource_modifications[resource.id] = ResourceModification(
                quantity=resource.quantity - amount,
                tick=self.world.tick,
                capacity=resource.capacity,
            )
        else:
            resource.quantity -= amount

    def projection(self, cx: int, cy: int) -> Chunk:
        base = self.cache.get(cx, cy)
        result = base.model_copy(deep=True)
        for i, t in enumerate(result.tiles):
            change = self.world.terrain_modifications.get(f"{t.position.x},{t.position.y}")
            if change:
                result.tiles[i] = change.model_copy(deep=True)
            result.tiles[i] = self.building_tile(result.tiles[i])
        for r in result.resources.values():
            r.quantity = quantity_at(self.world, r)
        return result

    def visible(self, center: Position, radius: int) -> tuple[list[Tile], list[Resource]]:
        if not self.world.config.infinite:
            return (
                [t for t in self.world.tiles if t.position.distance(center) <= radius],
                [r for r in self.world.resources.values() if r.position.distance(center) <= radius],
            )
        tiles, resources = [], []
        for cy in range((center.y - radius) // SIZE, (center.y + radius) // SIZE + 1):
            for cx in range((center.x - radius) // SIZE, (center.x + radius) // SIZE + 1):
                c = self.cache.get(cx, cy)
                tiles.extend(
                    self.tile(t.position) for t in c.tiles if t.position.distance(center) <= radius
                )
                resources.extend(
                    self.resource(r.id)
                    for r in c.resources.values()
                    if r.position.distance(center) <= radius
                )
        return tiles, resources

    def active_keys(self) -> list[str]:
        radius = self.world.config.active_radius
        keys = set()
        for a in self.world.agents.values():
            if a.alive:
                cx, cy = chunk_coord(a.position)
                keys.update(
                    chunk_key(cx + dx, cy + dy)
                    for dy in range(-radius, radius + 1)
                    for dx in range(-radius, radius + 1)
                )
        return sorted(keys)
