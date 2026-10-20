"""Purposeful terrain work using only the actor's local observation."""

from app.simulation.actions.provisions import carrying_room
from app.simulation.engineering.invention import best_tool
from app.simulation.models.domain import Action, Position, Terrain
from app.simulation.settlements.effects import building_usable


def earthwork_goals(o, add, approach):
    a = o.self_agent
    if a.hunger >= 55 or a.energy < 20:
        return
    reserved = {(b["position"]["x"], b["position"]["y"]) for b in o.buildings}
    reserved |= {(r.position.x, r.position.y) for r in o.resources}
    reserved |= {(c["position"]["x"], c["position"]["y"]) for c in o.crops}
    reserved |= {(p.x, p.y) for p in o.occupied}
    reserved.add((a.position.x, a.position.y))
    sites = [t for t in o.tiles if (t.position.x, t.position.y) not in reserved]
    s = o.settlement
    communal_stone = s["storage"]["stone"] if s else 0
    projects = ((s or {}).get("community") or {}).get("projects", [])
    demand = max([4] + [p["cost"].get("stone", 0) for p in projects if p["status"] == "active"])
    if (
        a.inventory.stone < 2
        and communal_stone < demand
        and carrying_room(a.inventory, "stone") > 0
        and best_tool(a, "mine")[1] >= 0.3
    ):
        rocks = [t for t in sites if t.terrain == Terrain.ROCK]
        if rocks:
            site = min(
                rocks, key=lambda t: (a.position.distance(t.position), t.position.y, t.position.x)
            )
            approach(
                "mine_building_material",
                site.position,
                {"material_need": 0.48, "resourcefulness": a.personality.resourcefulness * 0.15},
                Action.MINE,
                adjacent=True,
                target=site.position,
            )
    if (
        s
        and a.inventory.clay > 0
        and not any(b["kind"] == "farm" and building_usable(b) for b in o.buildings)
    ):
        center = Position.model_validate(s["center"])
        nearby = [t for t in sites if t.position.distance(center) <= 6]
        if not any(t.terrain in (Terrain.SOIL, Terrain.GRASS) for t in nearby):
            sites = [t for t in nearby if t.terrain in (Terrain.SAND, Terrain.PATH)]
            if sites:
                site = min(
                    sites,
                    key=lambda t: (a.position.distance(t.position), t.position.y, t.position.x),
                )
                approach(
                    "prepare_farmland",
                    site.position,
                    {"food_infrastructure": 0.56, "cooperation": a.personality.cooperation * 0.12},
                    Action.PLACE_BLOCK,
                    adjacent=True,
                    target=site.position,
                    item="clay",
                )
