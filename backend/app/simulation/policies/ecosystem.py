"""Choose living-system work from local observations, never from world state."""

from app.simulation.actions.ecosystem import crop_key
from app.simulation.engineering.invention import best_tool
from app.simulation.models.domain import RESOURCE_KINDS, Action, Position, Terrain


def ecosystem_goals(o, add, approach):
    a = o.self_agent
    room = a.inventory.capacity - a.inventory.total
    hunger = a.hunger / 100
    # Pick up actual visible belongings, including tools with their remaining wear.
    choices = []
    for drop in o.drops:
        if drop["expires"] <= o.tick:
            continue
        inv = drop["inventory"]
        items = [k for k in RESOURCE_KINDS if inv.get(k, 0)]
        items += [k for k, n in inv.get("products", {}).items() if n > 0]
        items += [
            k for k, n in inv.get("tools", {}).items() if n > 0 and not a.inventory.tools.get(k, 0)
        ]
        for item in items:
            is_food = item in ("food", "cooked_food")
            if room > 0 and (not is_food or a.inventory.food < 3):
                choices.append((is_food, drop, item))
    if choices:
        food, drop, item = max(
            choices, key=lambda v: (v[0], -a.position.distance(Position(**v[1]["position"])), v[2])
        )
        approach(
            "recover_food" if food else "recover_supplies",
            Position(**drop["position"]),
            {"food_reserve": 0.35 if food else 0.22, "hunger": hunger * 0.5 if food else 0},
            Action.PICK_UP,
            adjacent=True,
            entity_id=drop["id"],
            item=item,
        )
    ripe = [
        c
        for c in o.crops
        if c["growth"] == 80 and c["health"] > 0 and (c["owner_id"] == a.id or a.hunger >= 90)
    ]
    if ripe and room < 5 and a.inventory.food < 3:
        disposable = [k for k in RESOURCE_KINDS if k != "food" and getattr(a.inventory, k)]
        if disposable:
            item = max(disposable, key=lambda k: (getattr(a.inventory, k), k))
            add(
                "make_harvest_space",
                {"food_reserve": 0.82, "hunger": hunger * 0.15},
                Action.DISCARD,
                item=item,
                amount=min(5 - room, getattr(a.inventory, item)),
            )
    if ripe and room >= 5 and a.inventory.food < 4:
        crop = min(ripe, key=lambda c: a.position.distance(Position(**c["position"])))
        approach(
            "harvest_crop",
            Position(**crop["position"]),
            {"food_reserve": 0.4, "hunger": hunger * 0.45},
            Action.HARVEST,
            adjacent=True,
            target=Position(**crop["position"]),
        )
    own_crops = [c for c in o.crops if c["owner_id"] == a.id]
    thirsty = [c for c in own_crops if c["health"] > 0 and c["growth"] < 80 and c["moisture"] <= 50]
    if thirsty:
        crop = min(thirsty, key=lambda c: c["moisture"])
        factors = {"food_reserve": 0.38, "care": 0.2 * (1 - crop["moisture"] / 100)}
        if a.inventory.water:
            approach(
                "water_crop",
                Position(**crop["position"]),
                factors,
                Action.WATER_CROP,
                adjacent=True,
                target=Position(**crop["position"]),
            )
        elif room:
            water = [r for r in o.resources if r.kind == "water" and r.quantity > 0]
            if water:
                r = min(water, key=lambda r: a.position.distance(r.position))
                approach(
                    "supply_crop_water",
                    r.position,
                    factors,
                    Action.GATHER,
                    adjacent=True,
                    resource_id=r.id,
                )
    dead = next((c for c in own_crops if c["health"] == 0), None)
    if dead:
        p = Position(**dead["position"])
        approach("clear_crop", p, {"care": 0.3}, Action.HARVEST, adjacent=True, target=p)
    if a.hunger < 65 and len(own_crops) < 3 and a.position.distance(a.home) < 12:
        occupied = {crop_key(Position(**c["position"])) for c in o.crops}
        occupied |= {crop_key(Position(**b["position"])) for b in o.buildings}
        resource_positions = {crop_key(r.position) for r in o.resources}
        sites = [
            t
            for t in o.tiles
            if t.walkable
            and t.terrain in (Terrain.GRASS, Terrain.SOIL)
            and crop_key(t.position) not in occupied | resource_positions
            and t.position.distance(a.home) <= 8
        ]
        if a.inventory.seeds and sites:
            waters = [t.position for t in o.tiles if t.terrain == Terrain.WATER]
            site = min(
                sites,
                key=lambda t: (
                    min((t.position.distance(p) for p in waters), default=30),
                    t.terrain != Terrain.SOIL,
                    a.position.distance(t.position),
                    t.position.x,
                    t.position.y,
                ),
            )
            approach(
                "plant_crop",
                site.position,
                {
                    "future_food": 0.48,
                    "curiosity": a.personality.curiosity * 0.24,
                    "novelty": 0.12 if "plant_crop" not in a.habits else 0,
                },
                Action.PLANT if site.terrain == Terrain.SOIL else Action.TILL,
                adjacent=True,
                target=site.position,
            )
        elif room and not a.inventory.seeds:
            seeds = [r for r in o.resources if r.kind == "seeds" and r.quantity > 0]
            if seeds:
                r = min(seeds, key=lambda r: a.position.distance(r.position))
                approach(
                    "gather_seed",
                    r.position,
                    {
                        "future_food": 0.46,
                        "curiosity": a.personality.curiosity * 0.24,
                        "novelty": 0.12 if "gather_seed" not in a.habits else 0,
                    },
                    Action.GATHER,
                    adjacent=True,
                    resource_id=r.id,
                )
    animals = sorted(
        o.animals, key=lambda v: (a.position.distance(Position(**v["position"])), v["id"])
    )
    owned = [v for v in animals if v["owner_id"] == a.id]
    for animal in owned:
        adult = o.tick - animal["born_tick"] >= 240
        if adult and animal["hunger"] <= 40 and animal["produce_after"] <= o.tick and room:
            if animal["species"] != "sheep" or best_tool(a, "cut")[1] >= 0.3:
                approach(
                    "collect_animal",
                    Position(**animal["position"]),
                    {"food_reserve": 0.34, "resourcefulness": a.personality.resourcefulness * 0.15},
                    Action.COLLECT,
                    adjacent=True,
                    entity_id=animal["id"],
                )
                break
    fed = [
        v
        for v in owned
        if v["ready_until"] >= o.tick
        and v["breed_after"] <= o.tick
        and o.tick - v["born_tick"] >= 240
        and v["hunger"] <= 40
    ]
    pair = next(
        (
            (x, y)
            for x in fed
            for y in fed
            if x["id"] < y["id"]
            and x["species"] == y["species"]
            and Position(**x["position"]).distance(Position(**y["position"])) <= 2
        ),
        None,
    )
    if pair and len(owned) < 6:
        x, y = pair
        if a.position.distance(Position(**y["position"])) <= 2:
            approach(
                "breed_animals",
                Position(**x["position"]),
                {"future_food": 0.42, "curiosity": a.personality.curiosity * 0.16},
                Action.BREED,
                adjacent=True,
                entity_id=x["id"],
                resource_id=y["id"],
            )
    feedable = [
        v
        for v in animals
        if v["owner_id"] in (None, a.id)
        and (v["hunger"] >= 15 or v["ready_until"] < o.tick)
        and (v["owner_id"] == a.id or len(owned) < 3)
    ]
    if feedable and a.inventory.seeds and a.hunger < 65:
        v = feedable[0]
        approach(
            "tend_animal",
            Position(**v["position"]),
            {
                "future_food": 0.45,
                "curiosity": a.personality.curiosity * 0.24,
                "novelty": 0.12 if "tend_animal" not in a.habits else 0,
            },
            Action.FEED,
            adjacent=True,
            entity_id=v["id"],
        )
    wild = [v for v in animals if v["owner_id"] is None]
    if wild and a.hunger >= 65 and a.inventory.food == 0 and room >= 1:
        v = wild[0]
        if not a.combat or o.tick - a.combat.last_attack_tick >= 8:
            approach(
                "hunt_food",
                Position(**v["position"]),
                {"hunger": hunger * 0.5, "food_reserve": 0.24},
                Action.ATTACK,
                adjacent=True,
                entity_id=v["id"],
            )
    attacker = next(
        (
            p
            for p in o.peers
            if a.combat
            and p["id"] == a.combat.attacker_id
            and o.tick - a.combat.attacked_tick <= 32
        ),
        None,
    )
    if attacker:
        p = Position(**attacker["position"])
        if a.health >= 40 and a.energy >= 20 and (o.tick - a.combat.last_attack_tick >= 8):
            approach(
                "defend_self",
                p,
                {"immediate_survival": 0.9},
                Action.ATTACK,
                adjacent=True,
                peer_id=attacker["id"],
            )
        else:
            empty = [t.position for t in o.tiles if t.walkable and t.position not in o.occupied]
            if empty:
                target = max(empty, key=lambda v: (v.distance(p), -a.position.distance(v)))
                approach("flee_attack", target, {"immediate_survival": 1.0})
    if (
        a.hunger >= 95
        and a.inventory.food == 0
        and room > 0
        and a.personality.cooperation < 0.3
        and a.personality.risk_tolerance > 0.7
    ):
        peer = next((p for p in o.peers if p.get("need") is None), None)
        if peer:
            approach(
                "steal_to_survive",
                Position(**peer["position"]),
                {"hunger": hunger * 0.8},
                Action.STEAL,
                adjacent=True,
                peer_id=peer["id"],
                item="food",
            )
