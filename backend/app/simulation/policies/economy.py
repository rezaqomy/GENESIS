from app.simulation.actions.provisions import carrying_room
from app.simulation.engineering.housing import (
    HOUSING,
    best_design,
    construction_cost,
    propose_design,
    prototype_cost,
    tested,
)
from app.simulation.models.domain import RESOURCE_KINDS, Action, Inventory, Position
from app.simulation.settlements.effects import building_usable


def settlement_goals(o, add, approach, walkable):
    a, t, p = o.self_agent, o.self_agent.personality, o.self_agent.psychology
    s = o.settlement
    buildings = o.buildings
    center = Position.model_validate(s["center"]) if s else a.home
    distance = a.position.distance(center)
    storage = s["storage"] if s else {k: 0 for k in RESOURCE_KINDS}
    design = best_design(a)

    def count(kind):
        return sum(b["kind"] == kind and building_usable(b) for b in buildings)

    def supplies(cost, target):
        communal = s is not None and distance <= 8 and target.distance(center) <= 8
        return all(
            getattr(a.inventory, k) + (storage[k] if communal else 0) >= v for k, v in cost.items()
        )

    def transfer_position():
        positions = [center] + [
            Position.model_validate(b["position"])
            for b in buildings
            if b["kind"] == "storage" and building_usable(b)
        ]
        return min(positions, key=lambda v: (a.position.distance(v), v.y, v.x))

    cache = transfer_position()
    if s and s["food_reserves"] > 0 and a.inventory.food < 2:
        approach(
            "take_shared_food",
            cache,
            {
                "hunger": a.hunger / 100 * 0.55,
                "food_reserve": 0.36,
                "cooperation": t.cooperation * 0.1,
                "travel_cost": -min(1, distance / 30) * 0.15,
            },
            Action.WITHDRAW,
            adjacent=True,
            item="food",
            amount=1,
        )
    else:
        add(
            "take_shared_food",
            {},
            rejection="Shared food unavailable or carried reserve sufficient",
        )
    # An observed farm is useful only while somebody brings irrigation water.
    recent_water_trip = a.decision.selected_goal == "supply_farm" or (
        a.memory is not None
        and any(m.goal == "supply_farm" and 0 <= o.tick - m.tick <= 48 for m in a.memory.short_term)
    )
    continuing_water_trip = recent_water_trip and (not s or storage["water"] < 8)
    farm_needs_water = (s and count("farm") and storage["water"] < 8) or continuing_water_trip
    water = [r for r in o.resources if r.kind == "water" and r.quantity > 0]
    if not s and continuing_water_trip and a.inventory.water:
        approach("supply_farm", a.home, {"food_reserve": 0.68, "cooperation": t.cooperation * 0.1})
    elif (
        farm_needs_water
        and a.inventory.water
        and carrying_room(Inventory.model_validate(s["storage"]), "water", communal=True) > 0
    ):
        approach(
            "supply_farm",
            cache,
            {"food_reserve": 0.68, "cooperation": t.cooperation * 0.1},
            Action.STORE,
            adjacent=True,
            item="water",
            amount=min(
                8,
                a.inventory.water,
                s["storage"]["capacity"] - sum(storage[k] for k in RESOURCE_KINDS),
            ),
        )
    elif farm_needs_water and water and carrying_room(a.inventory, "water") > 0 and a.energy >= 8:
        resource = min(water, key=lambda r: (a.position.distance(r.position), r.id))
        approach(
            "supply_farm",
            resource.position,
            {"food_reserve": 0.65, "cooperation": t.cooperation * 0.1},
            Action.GATHER,
            adjacent=True,
            resource_id=resource.id,
        )
    elif continuing_water_trip and a.decision.target and a.inventory.water == 0:
        approach(
            "supply_farm",
            a.decision.target,
            {"food_reserve": 0.65, "cooperation": t.cooperation * 0.1},
        )
    else:
        add("supply_farm", {}, rejection="No observed farm irrigation shortage or accessible water")
    from app.simulation.policies.projects import propose_project

    building_plan = propose_project(o)
    study = None
    if building_plan and building_plan[0] in HOUSING:
        pending = building_plan[2]
        if pending and pending.get("design") and pending["durability"] > 0:
            from app.simulation.models.domain import ShelterDesign

            pending_design = ShelterDesign.model_validate(pending["design"])
            if not tested(a, pending_design):
                study = pending
    k = a.housing
    if design is None and study is None:
        examples = [
            b for b in buildings if b["kind"] in HOUSING and b.get("design") and building_usable(b)
        ]
        if examples:
            from app.simulation.models.domain import ShelterDesign

            study = min(
                examples, key=lambda b: a.position.distance(Position.model_validate(b["position"]))
            )
            pending_design = ShelterDesign.model_validate(study["design"])
    if k and k.studying_id and study is None:
        study = next((b for b in buildings if b["id"] == k.studying_id and b.get("design")), None)
        if study:
            from app.simulation.models.domain import ShelterDesign

            pending_design = ShelterDesign.model_validate(study["design"])
    # Hypotheses depend on personal trials and observed failures, never on ground truth scores.
    improving = bool(
        k
        and k.insights
        and design
        and (
            ("bracing" in k.insights and not design.bracing)
            or ("foundation" in k.insights and not design.raised_foundation)
            or ("roof" in k.insights and design.roof != "wood")
            or ("practice" in k.insights and k.practice < 60)
        )
    )
    curious = t.curiosity > 0.35 and (not k or not k.trials or o.tick - k.trials[-1].tick >= 72)
    experiment_needed = (
        design is None or improving or curious or bool(k and k.experiment) or study is not None
    )
    hypothesis = propose_design(a, o.seed, o.tick)
    if study:
        hypothesis = pending_design
    ongoing = bool(
        k
        and k.experiment == hypothesis
        and k.experiment_steps > 0
        and k.studying_id == (study["id"] if study else None)
    )
    experiment_cost = {} if study or ongoing else prototype_cost(hypothesis)
    experiment_ready = supplies(experiment_cost, a.position)
    recently_tested = bool(k and k.trials and o.tick - k.trials[-1].tick < 36)
    if (
        experiment_needed
        and experiment_ready
        and (design is None or ongoing or study or not recently_tested)
    ):
        approach(
            "experiment_shelter",
            Position.model_validate(study["position"]) if study else (cache if s else a.position),
            {
                "housing_need": 0.45,
                "curiosity": t.curiosity * 0.18,
                "ambition": t.ambition * 0.18,
                "failure_evidence": 0.2 if improving else 0,
            },
            Action.EXPERIMENT,
            adjacent=True,
            design=hypothesis,
            building_id=study["id"] if study else None,
        )
    else:
        add(
            "experiment_shelter",
            {},
            rejection="No current experiment need, materials, or recovery time",
        )
    project_cost = construction_cost(building_plan[0], design) if building_plan else {}
    missing = []
    for goal in ("build_shelter", "improve_settlement"):
        if (
            not s
            or not building_plan
            or (goal == "build_shelter") != (building_plan[0] == "shelter")
        ):
            add(goal, {}, rejection="No matching settlement project needed")
            continue
        kind, target, pending = building_plan
        selected_design = design
        if pending and pending.get("design") and pending["durability"] > 0:
            from app.simulation.models.domain import ShelterDesign

            selected_design = ShelterDesign.model_validate(pending["design"])
        cost = construction_cost(kind, selected_design)
        project_cost = cost
        if kind in HOUSING and (selected_design is None or not tested(a, selected_design)):
            add(goal, {}, rejection="No tested shelter design; experiment or study first")
            continue
        needs_revision = bool(
            k
            and selected_design
            and (
                ("bracing" in k.insights and not selected_design.bracing)
                or ("foundation" in k.insights and not selected_design.raised_foundation)
                or ("roof" in k.insights and selected_design.roof != "wood")
            )
        )
        if kind in HOUSING and needs_revision and (pending is None or pending["durability"] == 0):
            add(goal, {}, rejection="Investigate observed structural weaknesses before rebuilding")
            continue
        ready = (pending and pending["durability"] > 0) or supplies(cost, target)
        factors = {
            "ambition": t.ambition * 0.27,
            "cooperation": t.cooperation * 0.28,
            "comfort_preference": t.comfort_preference * 0.15,
            "housing_need": 0.24 if kind == "shelter" else 0.12,
            "travel_cost": -min(1, a.position.distance(target) / 40) * 0.15,
        }
        if ready:
            approach(
                goal,
                target,
                factors,
                Action.BUILD,
                adjacent=True,
                target=target,
                building_kind=kind,
                design=selected_design if kind in HOUSING else None,
            )
        else:
            add(goal, factors, rejection="Construction materials not yet available")
            communal = s is not None and distance <= 8 and target.distance(center) <= 8
            missing = [
                k
                for k, v in cost.items()
                if getattr(a.inventory, k) + (storage[k] if communal else 0) < v
            ]
    # Distant projects require physically hauling communal materials to the site.
    project_item = next((k for k in missing if storage[k] > 0), None)
    if s and project_item and building_plan and carrying_room(a.inventory, project_item) > 0:
        remaining = project_cost[project_item] - getattr(a.inventory, project_item)
        amount = min(4, remaining, storage[project_item], carrying_room(a.inventory, project_item))
        approach(
            "take_materials",
            cache,
            {
                "ambition": t.ambition * 0.28,
                "cooperation": t.cooperation * 0.28,
                "project_shortage": 0.24,
                "travel_cost": -min(1, distance / 30) * 0.15,
            },
            Action.WITHDRAW,
            adjacent=True,
            item=project_item,
            amount=amount,
        )
    else:
        add("take_materials", {}, rejection="No communal material needed for a distant project")
    reserved = (
        project_cost
        if building_plan and (building_plan[2] is None or building_plan[2]["durability"] == 0)
        else {}
    )
    surplus = next(
        (
            k
            for k in RESOURCE_KINDS
            if getattr(a.inventory, k) > (2 if k == "food" else reserved.get(k, 0))
        ),
        None,
    )
    communal = Inventory.model_validate(s["storage"]) if s else None
    store_room = carrying_room(communal, surplus, communal=True) if communal and surplus else 0
    if s and surplus and store_room > 0:
        approach(
            "store_resources",
            cache,
            {
                "cooperation": t.cooperation * 0.3,
                "inventory_pressure": a.inventory.total / a.inventory.capacity * 0.4,
                "loyalty": t.loyalty * 0.12,
                "material_supply": 0.25 if surplus != "food" else 0.06,
                "travel_cost": -min(1, distance / 30) * 0.1,
            },
            Action.STORE,
            adjacent=True,
            item=surplus,
            amount=min(
                4,
                store_room,
                getattr(a.inventory, surplus)
                - (2 if surplus == "food" else reserved.get(surplus, 0)),
            ),
        )
    else:
        add(
            "store_resources", {}, rejection="No surplus, storage full, or no settlement membership"
        )
    shortages = (
        [
            k
            for k in ("wood", "stone", "fiber", "fuel", "water", "seeds", "clay")
            if storage[k] < (6 if k == "wood" else 3)
        ]
        if s
        else ["wood", "fiber"]
    )
    experiment_missing = [
        key
        for key, value in experiment_cost.items()
        if experiment_needed
        and getattr(a.inventory, key) + (storage[key] if s and distance <= 8 else 0) < value
    ]
    wanted = list(dict.fromkeys(experiment_missing + missing + shortages))
    resources = [
        r
        for r in o.resources
        if r.quantity
        and r.kind in wanted
        and carrying_room(a.inventory, r.kind) > 0
        and getattr(a.inventory, r.kind) < (8 if r.kind == "wood" else 4)
    ]
    if resources and a.inventory.total < a.inventory.capacity and a.energy >= 8:
        resource = min(
            resources, key=lambda r: (wanted.index(r.kind), a.position.distance(r.position), r.id)
        )
        approach(
            "gather_resources",
            resource.position,
            {
                "cooperation": t.cooperation * 0.25,
                "ambition": t.ambition * 0.22,
                "construction_shortage": 0.24 if missing else 0.1,
                "resourcefulness": t.resourcefulness * 0.12,
                "travel_cost": -min(1, a.position.distance(resource.position) / 20) * 0.12,
                "hunger_cost": -a.hunger / 100 * 0.1,
            },
            Action.GATHER,
            adjacent=True,
            resource_id=resource.id,
        )
    else:
        add(
            "gather_resources",
            {},
            rejection="No visible needed materials, inventory full, or exhausted",
        )
    from app.simulation.policies.invention import invention_goals

    invention_goals(o, add, approach, supplies)
    fires = [
        b for b in buildings if b["kind"] == "campfire" and building_usable(b) and b["fuel"] < 5
    ]
    if fires and (storage["fuel"] + a.inventory.fuel) > 0:
        b = fires[0]
        approach(
            "refuel",
            Position.model_validate(b["position"]),
            {
                "safety_need": (1 - p.sense_of_safety) * 0.3,
                "cooperation": t.cooperation * 0.35,
                "warmth_need": 0.32,
            },
            Action.REFUEL,
            adjacent=True,
            building_id=b["id"],
        )
    else:
        add("refuel", {}, rejection="No low-fuel visible fire or fuel unavailable")
    remote = [b for b in buildings if b["kind"] == "remote_camp" and b["owner_id"] == a.id]
    pending_camp = next((b for b in remote if not building_usable(b)), None)
    candidate = (
        Position.model_validate(pending_camp["position"])
        if pending_camp
        else (a.decision.target if a.decision.selected_goal == "establish_camp" else a.position)
    )
    can_camp = (
        distance > 18
        and (
            (pending_camp is not None and pending_camp["durability"] > 0)
            or supplies(construction_cost("remote_camp", design), candidate)
        )
        and (len(remote) < 2 or pending_camp is not None)
        and design is not None
    )
    if can_camp:
        approach(
            "establish_camp",
            candidate,
            {
                "independence": t.independence * 0.32,
                "exposure": (1 - p.sense_of_safety) * 0.3,
                "fatigue": (1 - a.energy / 100) * 0.25,
                "loyalty_cost": -t.loyalty * 0.18,
            },
            Action.BUILD,
            adjacent=True,
            target=candidate,
            building_kind="remote_camp",
            design=design,
        )
    else:
        add(
            "establish_camp",
            {},
            rejection="Near settlement, lacking materials, or camp limit reached",
        )
