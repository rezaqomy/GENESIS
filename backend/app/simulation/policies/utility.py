"""Deterministic bounded goals. Policies propose; the writer commits and validates."""

import math

from app.simulation.chunks.generator import SIZE, sample
from app.simulation.models.domain import Action, AgentIntent, CandidateGoal, Position
from app.simulation.observation.builder import Observation
from app.simulation.pathfinding.astar import astar, local_waypoint, region_route

DEFAULT_WEIGHTS = {
    "need": 0.55,
    "trait": 0.25,
    "reward": 0.20,
    "travel": 0.18,
    "risk": 0.22,
    "social": 0.15,
    "scarcity": 0.24,
}


class UtilityPolicy:
    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = DEFAULT_WEIGHTS | (weights or {})

    def decide(self, o: Observation) -> AgentIntent:
        a, t, p = o.self_agent, o.self_agent.personality, o.self_agent.psychology
        occupied = {(v.x, v.y) for v in o.occupied}
        walkable = {
            (tile.position.x, tile.position.y) for tile in o.tiles if tile.walkable
        } - occupied
        walkable.add((a.position.x, a.position.y))
        hunger, tired = a.hunger / 100, 1 - a.energy / 100
        home_distance = a.position.distance(a.home)
        travel = min(1, home_distance / 80)
        full = a.inventory.total / a.inventory.capacity
        food = [r for r in o.resources if r.kind == "food" and r.quantity > 0]
        scarcity = 1 - min(1, sum(r.quantity for r in food) / 32)
        remembered_food = [
            Position(x=int(key.split(":")[1]), y=int(key.split(":")[2]))
            for key, quantity in a.food_memory.items()
            if quantity > 0
        ]
        candidates: list[CandidateGoal] = []
        plans: dict[str, tuple[Action, dict]] = {}

        def add(goal, factors, action=Action.IDLE, rejection=None, **kwargs):
            trait_keys = set(type(t).model_fields)
            for key, value in list(factors.items()):
                group = (
                    "trait"
                    if key in trait_keys
                    else "risk"
                    if key == "risk_cost"
                    else "travel"
                    if key == "travel_cost"
                    else "scarcity"
                    if key == "scarcity"
                    else "social"
                    if key in ("social_need", "crowding")
                    else "need"
                    if key
                    in (
                        "hunger",
                        "fatigue",
                        "loneliness",
                        "fear",
                        "homesickness",
                        "food_reserve",
                        "exhaustion",
                        "immediate_survival",
                    )
                    else "reward"
                )
                factors[key] = value * self.weights[group] / DEFAULT_WEIGHTS[group]
            score = max(0.0, min(1.0, sum(factors.values())))
            if a.decision.cooldowns.get(goal, 0) > o.tick:
                rejection = rejection or "Recovery cooldown"
            candidates.append(
                CandidateGoal(
                    goal=goal,
                    utility=round(score, 4),
                    factors={k: round(v, 4) for k, v in factors.items()},
                    rejection=rejection,
                )
            )
            plans[goal] = (action, kwargs)

        def approach(goal, destination, factors, action=Action.MOVE, adjacent=False, **kwargs):
            dx, dy = destination.x, destination.y
            goals = {(dx, dy)}
            if adjacent:
                goals |= {(dx + 1, dy), (dx - 1, dy), (dx, dy + 1), (dx, dy - 1)}
            path = astar(a.position, goals & walkable, walkable, o.path_budget)
            if path is None:
                path = local_waypoint(a.position, destination, walkable, o.path_budget)
            if path:
                move_kwargs = {k: v for k, v in kwargs.items() if k != "target"}
                add(
                    goal,
                    factors,
                    Action.MOVE,
                    target=path[0],
                    destination=destination,
                    **move_kwargs,
                )
            elif a.position.distance(destination) <= (1 if adjacent else 0):
                add(goal, factors, action, destination=destination, **kwargs)
            else:
                add(goal, factors, rejection="No reachable local route within planning budget")

        add(
            "eat",
            {"hunger": hunger * 0.9, "immediate_survival": 0.28 if hunger > 0.85 else 0.05},
            Action.EAT,
            rejection="No carried food" if not a.inventory.food else None,
        )
        add(
            "rest",
            {
                "fatigue": tired * 0.6,
                "comfort_preference": t.comfort_preference * 0.08,
                "exhaustion": 0.25 if a.energy < 12 else 0,
            },
            Action.REST,
            rejection="Energy already high" if a.energy > 86 else None,
        )
        paths = []
        for r in food:
            x, y = r.position.x, r.position.y
            goals = {(x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)} & walkable
            path = astar(a.position, goals, walkable, o.path_budget // 2)
            if path is not None:
                paths.append((len(path), r.id, path, r.position))
        food_factors = {
            "hunger": hunger * 0.52,
            "food_reserve": 0.35 * max(0, 1 - a.inventory.food / 3),
            "resourcefulness": t.resourcefulness * 0.1,
            "travel_cost": -0.06,
        }
        if paths and a.inventory.food < 3 and full < 1:
            _, rid, path, destination = min(paths, key=lambda v: (v[0], v[1]))
            add(
                "find_food",
                food_factors,
                Action.MOVE if path else Action.GATHER,
                **(
                    {"target": path[0], "destination": destination}
                    if path
                    else {"resource_id": rid, "destination": destination}
                ),
            )
        elif not paths and a.inventory.food < 2 and remembered_food:
            remembered = min(remembered_food, key=lambda v: (a.position.distance(v), v.y, v.x))
            approach("find_food", remembered, food_factors)
        else:
            add(
                "find_food",
                food_factors,
                rejection="Food reserve sufficient"
                if a.inventory.food >= 3
                else "No known reachable food",
            )
        social_need = p.loneliness * t.sociability
        home_factors = {
            "homesickness": p.homesickness * 0.45,
            "loyalty": t.loyalty * p.attachment * 0.25,
            "fatigue": tired * 0.26,
            "danger": p.fear * 0.26,
            "valuable_cargo": full * 0.16,
            "social_need": social_need * 0.3,
            "travel_cost": -travel * 0.1,
            "expedition_limit": 0.45
            if a.exploration_steps >= 60 + int(t.independence * 140)
            else 0,
        }
        if home_distance > 8:
            approach("return_home", a.home, home_factors, Action.REST, adjacent=True)
        else:
            add("return_home", home_factors, rejection="Already near home")
        if o.occupied:
            nearest = min(o.occupied, key=lambda v: (a.position.distance(v), v.y, v.x))
            approach(
                "socialize",
                nearest,
                {
                    "loneliness": social_need * 0.7,
                    "sociability": t.sociability * 0.25,
                    "crowding": -0.1 * max(0, len(o.occupied) - 4) / 6,
                },
                Action.SOCIALIZE,
                adjacent=True,
            )
        else:
            add("socialize", {"loneliness": social_need * 0.7}, rejection="No visible companions")
        if p.sense_of_safety < 0.4 and home_distance > 5:
            approach(
                "seek_safety",
                a.home,
                {
                    "fear": p.fear * 0.5,
                    "exposure": (1 - p.sense_of_safety) * 0.45,
                    "risk_aversion": (1 - t.risk_tolerance) * 0.2,
                },
                Action.REST,
                adjacent=True,
            )
        else:
            add("seek_safety", {"fear": p.fear}, rejection="Current location is safe enough")
        # Different incentives, no identity-based explorer/settler roles.
        explore_factors = {
            "curiosity": t.curiosity * 0.28,
            "independence": t.independence * 0.16,
            "exploration_drive": t.exploration_drive * 0.26,
            "scarcity": scarcity * 0.18,
            "crowding": max(0, len(o.occupied) - 4) * 0.015,
            "hunger_cost": -hunger * 0.24,
            "fatigue_cost": -tired * 0.18,
            "risk_cost": -(1 - t.risk_tolerance) * (1 - p.sense_of_safety) * 0.18,
            "attachment_cost": -t.loyalty * p.attachment * 0.1,
        }
        rejection = None
        budget = 60 + int(t.independence * 140)
        if a.energy < 25 or (a.hunger > 65 and a.inventory.food == 0):
            rejection = "Supplies or energy insufficient for exploration"
        if a.exploration_steps >= budget and home_distance > 8:
            rejection = "Exploration budget reached; resupply at home"
        destination = a.decision.target if a.decision.selected_goal == "explore" else None
        if destination is None or a.position.distance(destination) < 2:
            angle = sample(o.seed, int(a.id.split("-")[-1]), o.tick // 24, "exploration") * math.tau
            distance = 18 + int(t.exploration_drive * 50)
            destination = Position(
                x=a.position.x + round(math.cos(angle) * distance),
                y=a.position.y + round(math.sin(angle) * distance),
            )
            # Prefer an unknown region without granting knowledge of its contents.
            for _ in range(4):
                key = f"{destination.x // SIZE},{destination.y // SIZE}"
                if key not in a.known_chunks:
                    break
                angle += math.pi / 2
                destination = Position(
                    x=a.position.x + round(math.cos(angle) * distance),
                    y=a.position.y + round(math.sin(angle) * distance),
                )
        # Avoid repeatedly walking into the same frontier at a long river/obstacle.
        exploratory_tiles = walkable - {(v.x, v.y) for v in a.recent_positions}
        exploratory_tiles.add((a.position.x, a.position.y))
        path = local_waypoint(a.position, destination, exploratory_tiles, o.path_budget)
        add(
            "explore",
            explore_factors,
            Action.MOVE,
            target=path[0] if path else None,
            destination=destination,
            rejection=rejection or (None if path else "No reachable frontier"),
        )
        self.settlement_goals(o, add, approach, walkable)
        valid = [c for c in candidates if c.rejection is None]
        chosen = (
            max(valid, key=lambda c: (c.utility, c.goal))
            if valid
            else CandidateGoal(goal="observe", utility=0)
        )
        if a.hunger >= 85:
            survival = [c for c in valid if c.goal in ("eat", "find_food", "take_shared_food")]
            if survival:
                chosen = max(survival, key=lambda c: (c.utility, c.goal))
        previous = next((c for c in valid if c.goal == a.decision.selected_goal), None)
        urgent = (a.hunger >= 85 and chosen.goal in ("eat", "find_food", "take_shared_food")) or (
            a.energy < 12 and chosen.goal == "rest"
        )
        if previous and not urgent and a.decision.failures < 3:
            if o.tick < a.decision.commitment_until or chosen.utility < previous.utility + 0.09:
                chosen = previous
        action, kwargs = plans.get(chosen.goal, (Action.IDLE, {}))
        d = a.decision.model_copy(deep=True)
        switching = chosen.goal != d.selected_goal
        if switching:
            d.selected_tick = o.tick
            d.commitment_until = o.tick + 6
            d.origin_distance = a.position.distance(kwargs.get("destination", a.position))
        d.selected_goal = chosen.goal
        d.candidates = candidates
        d.factors = chosen.factors
        d.target = kwargs.get("destination")
        d.plan = [f"{action.value.lower()} toward goal"]
        if d.target:
            d.plan += [f"Region {key}" for key in region_route(a.position, d.target, budget=8)]
        d.progress = (
            round(max(0, min(1, 1 - a.position.distance(d.target) / max(1, d.origin_distance))), 3)
            if d.target
            else 0
        )
        return AgentIntent(actor_id=a.id, action=action, decision=d, **kwargs)

    def settlement_goals(self, o, add, approach, walkable):
        from app.simulation.policies.economy import settlement_goals

        settlement_goals(o, add, approach, walkable)
