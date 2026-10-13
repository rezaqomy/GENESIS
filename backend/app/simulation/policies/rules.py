import random
from typing import Protocol

from app.simulation.models.domain import Action, AgentIntent, Position
from app.simulation.observation.builder import Observation
from app.simulation.pathfinding.bfs import find_path


class AgentPolicy(Protocol):
    def decide(self, observation: Observation) -> AgentIntent: ...


class RulePolicy:
    def decide(self, observation: Observation) -> AgentIntent:
        a = observation.self_agent

        def intent(action, **kwargs):
            return AgentIntent(actor_id=a.id, action=action, **kwargs)

        if a.hunger >= 55 and a.inventory.food:
            return intent(Action.EAT)
        # Exhaustion must be resolved before attempting energy-consuming survival actions.
        if a.energy < 18:
            return intent(Action.REST)
        occupied = {(p.x, p.y) for p in observation.occupied}
        walkable = {
            (t.position.x, t.position.y) for t in observation.tiles if t.walkable
        } - occupied
        if a.inventory.food < 3 and a.inventory.total < a.inventory.capacity:
            candidates = []
            for r in sorted(observation.resources, key=lambda r: r.id):
                if r.kind != "food" or r.quantity == 0:
                    continue
                x, y = r.position.x, r.position.y
                goals = {(x, y), (x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)} & walkable
                path = find_path(a.position, goals, walkable)
                if path is not None:
                    candidates.append((len(path), r.id, path, r.position))
            if candidates:
                _, resource_id, path, destination = min(candidates, key=lambda c: (c[0], c[1]))
                if not path:
                    return intent(Action.GATHER, resource_id=resource_id, destination=destination)
                return intent(Action.MOVE, target=path[0], destination=destination)
        if a.energy < 40:
            return intent(Action.REST)
        destination = a.destination
        if destination and destination != a.position:
            path = find_path(a.position, {(destination.x, destination.y)}, walkable)
            if path:
                return intent(Action.MOVE, target=path[0], destination=destination)
        rng = random.Random(
            observation.seed + observation.tick * 104729 + int(a.id.split("-")[-1]) * 7919
        )
        choices = sorted(walkable)
        rng.shuffle(choices)
        for x, y in choices:
            if abs(x - a.position.x) + abs(y - a.position.y) < 4:
                continue
            path = find_path(a.position, {(x, y)}, walkable)
            if path:
                return intent(Action.MOVE, target=path[0], destination=Position(x=x, y=y))
        return intent(Action.IDLE)
