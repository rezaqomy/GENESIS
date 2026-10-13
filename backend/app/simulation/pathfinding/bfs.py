from collections import deque

from app.simulation.models.domain import Position


def find_path(
    start: Position, goals: set[tuple[int, int]], walkable: set[tuple[int, int]]
) -> list[Position] | None:
    origin = (start.x, start.y)
    queue = deque([origin])
    previous = {origin: None}
    while queue:
        current = queue.popleft()
        if current in goals:
            path = []
            while current != origin:
                path.append(Position(x=current[0], y=current[1]))
                current = previous[current]
            return list(reversed(path))
        x, y = current
        for target in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if target in walkable and target not in previous:
                previous[target] = current
                queue.append(target)
    return None
