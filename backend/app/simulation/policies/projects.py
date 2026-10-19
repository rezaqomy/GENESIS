"""Choose project sites from observed terrain and needs, never fixed map coordinates."""

from app.simulation.models.domain import Position
from app.simulation.settlements.effects import building_usable


def propose_project(o):
    a, s, p, t = o.self_agent, o.settlement, o.self_agent.psychology, o.self_agent.personality
    if not s:
        return None
    center = Position.model_validate(s["center"])
    buildings = o.buildings
    counts = {
        kind: sum(b["kind"] == kind and building_usable(b) for b in buildings)
        for kind in (
            "campfire",
            "shelter",
            "storage",
            "workbench",
            "farm",
            "watchtower",
            "road",
            "wooden_wall",
            "stone_wall",
            "bridge",
        )
    }
    needs = {
        "campfire": o.environment.get("cold", 0) * 0.6 + (1 - p.sense_of_safety) * 0.2,
        "shelter": (1 - o.local_effects.get("comfort", 0)) * 0.65 + t.comfort_preference * 0.25,
        "storage": s["storage"]["wood"] / max(1, s["storage"]["capacity"]) + t.cooperation * 0.3,
        "workbench": t.resourcefulness * 0.3 + t.ambition * 0.15,
        "farm": (1 - min(1, s["food_reserves"] / 12)) * 0.65 + t.cooperation * 0.25,
        "watchtower": t.exploration_drive * 0.3 + (1 - p.sense_of_safety) * 0.2,
        "road": t.resourcefulness * 0.25 + t.cooperation * 0.15,
        "wooden_wall": (1 - p.sense_of_safety) * 0.35 + t.comfort_preference * 0.15,
        "stone_wall": (1 - p.sense_of_safety) * 0.35 + t.ambition * 0.15,
        "bridge": t.exploration_drive * 0.35 + t.independence * 0.2,
    }
    occupied = {(b["position"]["x"], b["position"]["y"]) for b in buildings}
    people = {(p.x, p.y) for p in o.occupied} | {(a.position.x, a.position.y)}
    options = []
    for kind, need in needs.items():
        pending = next((b for b in buildings if b["kind"] == kind and not building_usable(b)), None)
        if pending:
            target = Position.model_validate(pending["position"])
        else:
            sites = [
                tile.position
                for tile in o.tiles
                if (tile.position.x, tile.position.y) not in occupied
                and tile.position.distance(center) <= 8
                and (tile.terrain.value == "water" if kind == "bridge" else tile.walkable)
                and (kind not in ("shelter", "farm") or tile.terrain.value in ("grass", "soil"))
                and (kind != "shelter" or tile.position.distance(center) >= 2)
                and (
                    kind not in ("wooden_wall", "stone_wall", "watchtower")
                    or (tile.position.x, tile.position.y) not in people
                )
            ]
            if not sites:
                continue
            target = min(sites, key=lambda p: (a.position.distance(p), p.y, p.x))
        score = need / (1 + counts[kind]) - a.position.distance(target) * 0.008
        if pending:
            score += 0.12
        task = a.task
        if (
            task
            and task.status == "active"
            and task.kind == "construction"
            and task.target == target
        ):
            score += 0.5
        options.append((score, kind, target, pending))
    if not options:
        return None
    _, kind, target, pending = max(options, key=lambda row: (row[0], row[1]))
    return kind, target, pending
