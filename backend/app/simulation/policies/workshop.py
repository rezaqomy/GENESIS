"""Local, evidence-driven invention and use. No calls to the physics evaluator."""

from app.simulation.engineering.assemblies import (
    CAPABILITIES,
    MATERIALS,
    PRODUCTS,
    cost,
    design_id,
    propose,
    quantity,
)
from app.simulation.models.domain import RESOURCE_KINDS, Action, Position, TradeOffer
from app.simulation.settlements.effects import building_usable


def workshop_goals(o, add, approach):
    a, k = o.self_agent, o.self_agent.workshop
    if a.hunger >= 65 or a.energy < 18:
        return
    s = o.settlement
    storage = (s or {}).get("storage", {})
    devices = [b for b in o.buildings if b.get("assembly") and building_usable(b)]
    waters = [t.position for t in o.tiles if t.terrain.value == "water"]
    farms = [b for b in o.buildings if b["kind"] == "farm" and building_usable(b)]
    needs = {
        "catch": 0.85 if waters and a.inventory.food < 2 else 0.25 if waters else 0,
        "water": 0.75 if farms and storage.get("water", 0) < 4 else 0.1,
        "heat": 0.8 if a.inventory.ore or storage.get("ore", 0) else 0.5,
        "cultivate": 0.65 if farms else 0.05,
        "shelter": 0.55 if o.local_effects.get("comfort", 0) < 0.3 else 0.05,
        "storage": 0.4 if a.inventory.total > a.inventory.capacity * 0.65 else 0.1,
    }
    known = {
        p: max([0] + [t.measured.get(p, 0) for t in (k.trials if k else [])]) for p in CAPABILITIES
    }
    purpose = max(CAPABILITIES, key=lambda p: (needs[p] - known[p], p))
    available = {
        m: quantity(a.inventory, m) + storage.get(m, 0) + storage.get("products", {}).get(m, 0)
        for m in MATERIALS
    }
    hypothesis = propose(a, o.seed, o.tick, available, purpose)
    study = None
    if not (k and k.experiment):
        unseen = [
            b
            for b in devices
            if not k
            or not any(
                design_id(t.design) == design_id_from_record(b["assembly"]["design"])
                for t in k.trials
            )
        ]
        if unseen and a.personality.sociability > 0.4:
            study = min(
                unseen, key=lambda b: a.position.distance(Position.model_validate(b["position"]))
            )
            from app.simulation.models.domain import AssemblyDesign

            hypothesis = AssemblyDesign.model_validate(study["assembly"]["design"])
    ongoing = bool(k and k.experiment)
    recent = bool(k and k.trials and o.tick - k.trials[-1].tick < 36)
    ready = hypothesis and all(available.get(m, 0) >= n for m, n in cost(hypothesis).items())
    if ongoing or (ready and not recent):
        target = (
            Position.model_validate(study["position"])
            if study
            else Position.model_validate(s["center"])
            if s and not ongoing
            else a.position
        )
        approach(
            "experiment_assembly",
            target,
            {
                "curiosity": a.personality.curiosity * 0.32,
                "novelty": 0.22,
                "equipment_need": max(0.05, needs[purpose] - known[purpose]) * 0.25,
                "experiment_progress": 0.4 if ongoing else 0,
            },
            Action.EXPERIMENT_ASSEMBLY,
            adjacent=True,
            assembly_design=hypothesis,
            building_id=study["id"] if study else None,
        )
    else:
        add(
            "experiment_assembly",
            {},
            rejection="Need materials, a fresh hypothesis or recovery time",
        )
    # A discovered device is fabricated only when its measured properties address a need.
    occupied = {(b["position"]["x"], b["position"]["y"]) for b in o.buildings}
    occupied |= {(r.position.x, r.position.y) for r in o.resources}
    occupied |= {(c["position"]["x"], c["position"]["y"]) for c in o.crops}
    occupied |= {(p.x, p.y) for p in o.occupied}
    sites = [
        t.position
        for t in o.tiles
        if t.walkable
        and (t.position.x, t.position.y) not in occupied
        and (s is None or t.position.distance(Position.model_validate(s["center"])) <= 8)
    ]
    options = []
    for t in k.trials if k else []:
        if any(
            design_id_from_record(b["assembly"]["design"]) == design_id(t.design) for b in devices
        ):
            continue
        if any(available.get(m, 0) < n for m, n in cost(t.design).items()):
            continue
        capability = max(CAPABILITIES, key=lambda p: needs[p] * t.measured.get(p, 0))
        score = needs[capability] * t.measured.get(capability, 0)
        existing = max([0] + [b["assembly"]["measured"].get(capability, 0) for b in devices])
        if t.measured.get(capability, 0) < 0.3 or t.measured.get(capability, 0) <= existing + 0.05:
            continue
        possible = sites
        if capability in ("catch", "water"):
            possible = [p for p in sites if any(p.distance(w) == 1 for w in waters)]
        if capability == "cultivate":
            possible = [
                p
                for p in sites
                if any(p.distance(Position.model_validate(b["position"])) <= 1 for b in farms)
            ]
        if possible:
            site = min(possible, key=lambda p: (a.position.distance(p), p.y, p.x))
            options.append((score, design_id(t.design), t, site))
    if options:
        score, _, trial, site = max(
            options, key=lambda v: (bool(k and k.planned and design_id(k.planned) == v[1]), *v[:2])
        )
        # Hauling is explicit: communal supplies cannot be consumed from a remote build site.
        personal_ready = all(quantity(a.inventory, m) >= n for m, n in cost(trial.design).items())
        at_cache = s and a.position.distance(Position.model_validate(s["center"])) <= 2
        if not personal_ready and s:
            missing = next(
                (
                    m
                    for m, n in cost(trial.design).items()
                    if m in RESOURCE_KINDS
                    and quantity(a.inventory, m) < n
                    and storage.get(m, 0) > 0
                ),
                None,
            )
            if missing and a.inventory.total < a.inventory.capacity - 3:
                amount = min(
                    cost(trial.design)[missing] - quantity(a.inventory, missing),
                    storage[missing],
                    a.inventory.capacity - a.inventory.total - 3,
                    8,
                )
                approach(
                    "supply_assembly",
                    Position.model_validate(s["center"]),
                    {"productive_project": 0.78},
                    Action.WITHDRAW,
                    adjacent=True,
                    item=missing,
                    amount=amount,
                    assembly_design=trial.design,
                )
        if personal_ready or (at_cache and a.position.distance(site) <= 1):
            approach(
                "fabricate_assembly",
                site,
                {"productive_project": 0.66 + score * 0.3},
                Action.ASSEMBLE,
                adjacent=True,
                target=site,
                assembly_design=trial.design,
            )
    for capability in ("catch", "water", "cultivate"):
        usable = []
        for b in devices:
            if b["assembly"]["measured"].get(capability, 0) < 0.3:
                continue
            wait = 120 if capability == "cultivate" else 24 if capability == "catch" else 8
            if o.tick - b.get("last_operated_tick", -1000) < wait:
                continue
            pos = Position.model_validate(b["position"])
            depleted = {
                (m.target.x, m.target.y)
                for m in (a.memory.short_term if a.memory else [])
                if m.kind == "failure"
                and m.target
                and "patch is depleted" in m.text
                and o.tick - m.tick < 120
            }
            target = next(
                (p for p in waters if p.distance(pos) == 1 and (p.x, p.y) not in depleted), None
            )
            if capability != "cultivate" and target is None:
                continue
            if capability == "cultivate" and (not a.inventory.seeds or not a.inventory.water):
                continue
            if capability == "catch" and (
                a.inventory.food >= 3 or a.inventory.total >= a.inventory.capacity
            ):
                continue
            if capability == "water" and (
                a.inventory.water >= 2 or a.inventory.total >= a.inventory.capacity
            ):
                continue
            usable.append((a.position.distance(pos), b["id"], b, target))
        if usable:
            _, _, b, target = min(usable, key=lambda v: v[:2])
            need = (
                0.65 if capability == "catch" and a.inventory.food == 0 else needs[capability] * 0.6
            )
            approach(
                "operate_" + capability,
                Position.model_validate(b["position"]),
                {"production_need": need, "resourcefulness": a.personality.resourcefulness * 0.12},
                Action.OPERATE,
                adjacent=True,
                building_id=b["id"],
                item=capability,
                target=target,
            )
    fires = [
        b
        for b in o.buildings
        if building_usable(b)
        and (
            (b["kind"] == "campfire" and b["fuel"] > 0)
            or (
                b.get("assembly")
                and b["assembly"]["measured"].get("heat", 0) > 0.1
                and a.inventory.fuel
            )
        )
    ]
    heat_options = []
    for b in fires:
        level = b["assembly"]["measured"].get("heat", 0) if b.get("assembly") else 0.35
        band = "hot" if level >= 0.7 else "warm" if level >= 0.55 else "low"
        for item in ("clay", "ore", "food", "wood"):
            key = f"{item}:{band}"
            result = (k.transformations if k else {}).get(key)
            if (
                not quantity(a.inventory, item)
                or result == "input lost; insufficient heat"
                or (
                    item == "food"
                    and (a.inventory.food < 2 or a.inventory.products.get("cooked_food", 0) >= 2)
                )
                or (item == "wood" and a.inventory.fuel >= 3)
                or (result in PRODUCTS and a.inventory.products.get(result, 0) >= 3)
            ):
                continue
            heat_options.append((0.5 if result else 0.35 + a.personality.curiosity * 0.2, b, item))
    if heat_options:
        score, b, item = max(heat_options, key=lambda v: (v[0], v[1]["id"], v[2]))
        approach(
            "heat_material",
            Position.model_validate(b["position"]),
            {"transformation_value": score},
            Action.HEAT,
            adjacent=True,
            building_id=b["id"],
            item=item,
        )
    # Public offers reveal the goods being offered, never the partner's private inventory.
    offered = [p for p in o.peers if p.get("trade_offer") and p["trade_offer"]["expires"] > o.tick]
    for peer in offered:
        offer = peer["trade_offer"]
        if quantity(a.inventory, offer["want_item"]) >= offer["want_amount"] + (
            1 if offer["want_item"] == "food" else 0
        ):
            if (
                a.inventory.total - offer["want_amount"] + offer["give_amount"]
                <= a.inventory.capacity
            ):
                add(
                    "barter",
                    {"exchange_value": 0.48, "cooperation": a.personality.cooperation * 0.12},
                    Action.ACCEPT_TRADE,
                    peer_id=peer["id"],
                    item=offer["id"],
                )
                break
    else:
        old_offer = k.offer if k else None
        if not old_offer or old_offer.expires <= o.tick:
            wanted = next(
                (m for m in ("fiber", "clay", "stone", "wood") if quantity(a.inventory, m) == 0),
                None,
            )
            surplus = next((m for m in RESOURCE_KINDS if quantity(a.inventory, m) >= 3), None)
            peers = [
                p
                for p in o.peers
                if a.position.distance(Position.model_validate(p["position"])) <= 1
            ]
            if wanted and surplus and peers:
                peer = peers[0]
                offer = TradeOffer(
                    id=f"barter:{a.id}:{o.tick}",
                    peer_id=peer["id"],
                    give_item=surplus,
                    want_item=wanted,
                    expires=o.tick + 96,
                )
                add(
                    "barter",
                    {"exchange_value": 0.4, "sociability": a.personality.sociability * 0.12},
                    Action.OFFER_TRADE,
                    peer_id=peer["id"],
                    trade=offer,
                )

    ruins = [
        b
        for b in o.buildings
        if b.get("assembly")
        and b["owner_id"] == a.id
        and b["durability"] == 0
        and not b.get("salvaged")
    ]
    if ruins:
        b = min(ruins, key=lambda b: a.position.distance(Position.model_validate(b["position"])))
        d_cost = cost_from_record(b["assembly"]["design"])
        if a.inventory.total + sum(n // 2 for n in d_cost.values()) <= a.inventory.capacity:
            approach(
                "salvage_assembly",
                Position.model_validate(b["position"]),
                {"recovery_value": 0.55},
                Action.DISMANTLE,
                adjacent=True,
                building_id=b["id"],
            )


def cost_from_record(record):
    from app.simulation.models.domain import AssemblyDesign

    return cost(AssemblyDesign.model_validate(record))


def design_id_from_record(record):
    from app.simulation.models.domain import AssemblyDesign

    return design_id(AssemblyDesign.model_validate(record))
