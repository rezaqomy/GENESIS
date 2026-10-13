from app.simulation.models.domain import RESOURCE_KINDS, Action, Position
from app.simulation.settlements.effects import BUILD_COSTS, TOOL_COSTS


def settlement_goals(o, add, approach, walkable):
    a, t, p = o.self_agent, o.self_agent.personality, o.self_agent.psychology
    s = o.settlement
    buildings = o.buildings
    center = Position.model_validate(s["center"]) if s else a.home
    distance = a.position.distance(center)
    storage = s["storage"] if s else {k: 0 for k in RESOURCE_KINDS}

    def count(kind):
        return sum(b["kind"] == kind and b["progress"] == 100 for b in buildings)

    def supplies(cost, target):
        communal = s is not None and distance <= 8 and target.distance(center) <= 8
        return all(
            getattr(a.inventory, k) + (storage[k] if communal else 0) >= v for k, v in cost.items()
        )

    def transfer_position():
        positions = [center] + [
            Position.model_validate(b["position"])
            for b in buildings
            if b["kind"] == "storage" and b["progress"] == 100
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
    desired = [
        ("shelter", 2, [(2, 2), (-2, -4)]),
        ("storage", 1, [(-3, 2)]),
        ("workbench", 1, [(-3, -1)]),
        ("farm", 1, [(6, 5)]),
        ("watchtower", 1, [(4, -3)]),
        ("road", 1, [(1, 0)]),
        ("wooden_wall", 1, [(4, 4)]),
        ("stone_wall", 1, [(5, 4)]),
        ("bridge", 2, [(10, 0), (11, 0)]),
    ]
    building_plan = None
    for kind, number, sites in desired:
        if count(kind) < number:
            pending = next(
                (b for b in buildings if b["kind"] == kind and b["progress"] < 100), None
            )
            target = (
                Position.model_validate(pending["position"])
                if pending
                else Position(
                    x=center.x + sites[min(count(kind), len(sites) - 1)][0],
                    y=center.y + sites[min(count(kind), len(sites) - 1)][1],
                )
            )
            building_plan = (kind, target, pending)
            break
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
        cost = BUILD_COSTS[kind]
        ready = pending or supplies(cost, target)
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
    if s and project_item and building_plan and a.inventory.total < a.inventory.capacity:
        remaining = BUILD_COSTS[building_plan[0]][project_item] - getattr(a.inventory, project_item)
        amount = min(4, remaining, storage[project_item], a.inventory.capacity - a.inventory.total)
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
    reserved = BUILD_COSTS[building_plan[0]] if building_plan and building_plan[2] is None else {}
    surplus = next(
        (
            k
            for k in RESOURCE_KINDS
            if getattr(a.inventory, k) > (2 if k == "food" else reserved.get(k, 0))
        ),
        None,
    )
    if s and surplus and s["storage"]["capacity"] > sum(storage[k] for k in RESOURCE_KINDS):
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
    wanted = list(dict.fromkeys(missing + shortages))
    resources = [r for r in o.resources if r.quantity and r.kind in wanted]
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
    benches = [b for b in buildings if b["kind"] == "workbench" and b["progress"] == 100]
    tool = next((k for k in TOOL_COSTS if not a.inventory.tools.get(k, 0)), None)
    if (
        benches
        and tool
        and supplies(TOOL_COSTS[tool], Position.model_validate(benches[0]["position"]))
    ):
        target = Position.model_validate(benches[0]["position"])
        approach(
            "craft_tools",
            target,
            {
                "ambition": t.ambition * 0.3,
                "resourcefulness": t.resourcefulness * 0.3,
                "equipment_need": 0.25,
                "hunger_cost": -a.hunger / 100 * 0.15,
            },
            Action.CRAFT,
            adjacent=True,
            item=tool,
        )
    else:
        add("craft_tools", {}, rejection="Tool already equipped or workbench/materials unavailable")
    fires = [
        b for b in buildings if b["kind"] == "campfire" and b["progress"] == 100 and b["fuel"] < 5
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
    pending_camp = next((b for b in remote if b["progress"] < 100), None)
    candidate = (
        Position.model_validate(pending_camp["position"])
        if pending_camp
        else (a.decision.target if a.decision.selected_goal == "establish_camp" else a.position)
    )
    can_camp = (
        distance > 18
        and (pending_camp is not None or supplies(BUILD_COSTS["remote_camp"], candidate))
        and (len(remote) < 2 or pending_camp is not None)
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
        )
    else:
        add(
            "establish_camp",
            {},
            rejection="Near settlement, lacking materials, or camp limit reached",
        )
