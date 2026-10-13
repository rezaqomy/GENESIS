"""Version 2: absolute-coordinate value noise, independent of chunk/request order."""

import hashlib
import math
from functools import lru_cache

from app.simulation.models.domain import Chunk, Position, Resource, Terrain, Tile

SIZE = 32


def chunk_coord(position: Position) -> tuple[int, int]:
    return position.x // SIZE, position.y // SIZE


def chunk_key(cx: int, cy: int) -> str:
    return f"{cx},{cy}"


@lru_cache(maxsize=32768)
def sample(seed: int, x: int, y: int, salt: str = "terrain") -> float:
    value = hashlib.blake2b(f"{seed}:{x}:{y}:{salt}".encode(), digest_size=8).digest()
    return int.from_bytes(value, "little") / (2**64 - 1)


def noise(seed: int, x: int, y: int, scale: int, salt: str) -> float:
    gx, gy = math.floor(x / scale), math.floor(y / scale)
    fx, fy = x / scale - gx, y / scale - gy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = sample(seed, gx, gy, salt), sample(seed, gx + 1, gy, salt)
    c, d = sample(seed, gx, gy + 1, salt), sample(seed, gx + 1, gy + 1, salt)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def terrain_at(seed: int, x: int, y: int, version: int = 2) -> Terrain:
    if version != 2:
        raise ValueError("Unsupported chunk generator version")
    # A small deterministic starting clearing, blended into the surrounding wilderness.
    if abs(x) <= 14 and abs(y) <= 14:
        if 10 <= x <= 11 + int(math.sin(y * 0.25)):
            return Terrain.WATER
        if 6 <= x <= 9 and 3 <= y <= 9:
            return Terrain.SOIL
        if x <= -8 and y <= 7:
            return Terrain.FOREST
        if 8 <= x <= 12 and -10 <= y <= -6:
            return Terrain.ROCK
        if abs(x) <= 6 and abs(y) <= 6:
            return Terrain.GRASS
    moisture = noise(seed, x, y, 64, "moisture")
    elevation = noise(seed, x, y, 80, "elevation") * 0.75 + noise(seed, x, y, 24, "detail") * 0.25
    river = abs(noise(seed, x, y, 96, "river") - 0.5)
    if river < 0.023 or (moisture > 0.78 and elevation < 0.45):
        return Terrain.WATER
    if river < 0.04:
        return Terrain.SAND
    if elevation > 0.76:
        return Terrain.MOUNTAIN
    if elevation > 0.66:
        return Terrain.ROCK
    if moisture > 0.56:
        return Terrain.FOREST
    if moisture > 0.45 and elevation < 0.47:
        return Terrain.SOIL
    return Terrain.GRASS


def resource_at(seed: int, x: int, y: int, terrain: Terrain) -> Resource | None:
    kind = None
    n = sample(seed, x, y, "resource")
    # Guaranteed, regenerable essential resources around the first clearing.
    starters = {
        (-5, -3): "wood",
        (-5, 3): "wood",
        (-4, 7): "wood",
        (-7, -1): "wood",
        (4, -4): "food",
        (-3, -5): "food",
        (4, 3): "food",
        (1, 6): "food",
        (-6, 5): "food",
        (8, -7): "stone",
        (9, -8): "ore",
        (7, 5): "seeds",
        (6, 6): "fiber",
        (9, 0): "clay",
        (-8, 8): "fuel",
    }
    if (x, y) in starters:
        kind = starters[x, y]
    elif abs(x) <= 3 and abs(y) <= 3:
        return None
    elif terrain == Terrain.WATER and n < 0.07:
        kind = "water"
    elif terrain in (Terrain.ROCK, Terrain.MOUNTAIN) and n < 0.16:
        kind = "ore" if n < 0.025 else "fuel" if n < 0.05 else "stone"
    elif terrain == Terrain.FOREST:
        kind = "wood" if n < 0.12 else "food" if n < 0.15 else "fiber" if n < 0.17 else None
    elif terrain == Terrain.SOIL:
        kind = "seeds" if n < 0.025 else "food" if n < 0.075 else "fiber" if n < 0.095 else None
    elif terrain == Terrain.SAND and n < 0.035:
        kind = "clay"
    elif terrain == Terrain.GRASS and n < 0.06:
        kind = "food" if n < 0.023 else "fiber" if n < 0.04 else "wood"
    if kind is None:
        return None
    capacity = 100 if kind == "water" else 10 if kind == "wood" else 8
    return Resource(
        id=f"r:{x}:{y}:{kind}",
        position=Position(x=x, y=y),
        kind=kind,
        quantity=capacity,
        capacity=capacity,
    )


def generate_chunk(seed: int, cx: int, cy: int, version: int = 2) -> Chunk:
    tiles, resources = [], {}
    for ly in range(SIZE):
        for lx in range(SIZE):
            x, y = cx * SIZE + lx, cy * SIZE + ly
            terrain = terrain_at(seed, x, y, version)
            tiles.append(
                Tile(
                    position=Position(x=x, y=y),
                    terrain=terrain,
                    walkable=terrain not in (Terrain.WATER, Terrain.ROCK, Terrain.MOUNTAIN),
                )
            )
            resource = resource_at(seed, x, y, terrain)
            if resource:
                resources[resource.id] = resource
    return Chunk(
        key=chunk_key(cx, cy),
        cx=cx,
        cy=cy,
        generator_version=version,
        tiles=tiles,
        resources=resources,
    )
