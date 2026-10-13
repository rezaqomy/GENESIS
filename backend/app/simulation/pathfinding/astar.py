"""Bounded local A* and region waypoints; no whole-world graph allocation."""

import heapq

from app.simulation.chunks.generator import SIZE, chunk_coord
from app.simulation.models.domain import Position


def astar(
    start: Position,
    goals: set[tuple[int, int]],
    walkable: set[tuple[int, int]],
    budget: int = 600,
    costs: dict[tuple[int, int], float] | None = None,
) -> list[Position] | None:
    if not goals:
        return None
    origin = (start.x, start.y)

    def heuristic(p):
        return min(abs(p[0] - g[0]) + abs(p[1] - g[1]) for g in goals) * 0.5

    queue = [(heuristic(origin), 0.0, origin)]
    previous, distances = {origin: None}, {origin: 0.0}
    expanded = 0
    while queue and expanded < budget:
        _, cost, p = heapq.heappop(queue)
        if cost > distances[p]:
            continue
        expanded += 1
        if p in goals:
            path = []
            while p != origin:
                path.append(Position(x=p[0], y=p[1]))
                p = previous[p]
            return list(reversed(path))
        x, y = p
        for target in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if target not in walkable:
                continue
            next_cost = cost + (costs or {}).get(target, 1.0)
            if next_cost < distances.get(target, float("inf")):
                distances[target] = next_cost
                previous[target] = p
                heapq.heappush(queue, (next_cost + heuristic(target), next_cost, target))
    return None


def region_route(start: Position, destination: Position, budget: int = 128) -> list[str]:
    """Coarse chunk corridor, bounded and used only as a plan (not knowledge of terrain)."""
    cx, cy = chunk_coord(start)
    dx, dy = chunk_coord(destination)
    result = []
    while (cx, cy) != (dx, dy) and len(result) < budget:
        if cx != dx:
            cx += 1 if dx > cx else -1
        else:
            cy += 1 if dy > cy else -1
        result.append(f"{cx},{cy}")
    return result


def local_waypoint(
    start: Position, destination: Position, walkable: set[tuple[int, int]], budget: int = 600
) -> list[Position] | None:
    if (destination.x, destination.y) in walkable:
        return astar(start, {(destination.x, destination.y)}, walkable, budget)
    # Explore a reachable frontier toward the next chunk corridor, then replan next tick.
    route = region_route(start, destination, budget=4)
    target = destination
    if route:
        cx, cy = map(int, route[0].split(","))
        target = Position(x=cx * SIZE + SIZE // 2, y=cy * SIZE + SIZE // 2)
    candidates = sorted(
        walkable, key=lambda p: (abs(p[0] - target.x) + abs(p[1] - target.y), p[1], p[0])
    )
    for candidate in candidates[:6]:
        path = astar(start, {candidate}, walkable, budget // 6)
        if path:
            return path
    return None
