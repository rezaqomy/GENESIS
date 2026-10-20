from app.simulation.actions.provisions import carrying_room
from app.simulation.engineering.housing import (
    HOUSING,
    best_design,
    construction_cost,
    knowledge,
    prototype_cost,
    tested,
    workmanship,
)
from app.simulation.models.domain import RESOURCE_KINDS, Action, Building, WorldState
from app.simulation.settlements.effects import BUILD_COSTS, TOOL_COSTS, building_usable


def storage_access(world, agent):
    s = world.settlements.get(agent.settlement_id or "")
    if s is None:
        return None
    # A communal camp cache plus constructed storage chests; access has a physical radius.
    positions = [s.center] + [
        world.buildings[k].position
        for k in s.buildings
        if k in world.buildings
        and world.buildings[k].kind == "storage"
        and building_usable(world.buildings[k])
    ]
    return s if any(agent.position.distance(p) <= 2 for p in positions) else None


def materials(world, agent, target):
    s = world.settlements.get(agent.settlement_id or "")
    sources = [agent.inventory]
    if s and agent.position.distance(s.center) <= 8 and target.distance(s.center) <= 8:
        sources.append(s.storage)
    return sources


def affordable(cost, sources):
    return all(
        sum(getattr(source, key) for source in sources) >= amount for key, amount in cost.items()
    )


def pay(cost, sources):
    for key, amount in cost.items():
        for source in sources:
            take = min(amount, getattr(source, key))
            setattr(source, key, getattr(source, key) - take)
            amount -= take


def validate_construction(world: WorldState, intent, access) -> str | None:
    a = world.agents[intent.actor_id]
    if intent.action == Action.EXPERIMENT_TOOL or (
        intent.action == Action.CRAFT and world.config.infinite
    ):
        from app.simulation.engineering.invention import validate

        return validate(world, a, intent)
    if intent.action == Action.EXPERIMENT:
        if a.energy < 3:
            return "Not enough energy for an experiment"
        if intent.design is None:
            return "An experiment requires a material and support hypothesis"
        if intent.building_id:
            b = world.buildings.get(intent.building_id)
            if not b or b.kind not in HOUSING or b.design != intent.design:
                return "Study requires a real observable shelter design"
            if a.position.distance(b.position) > 1:
                return "Study structure must be within one tile"
        else:
            ongoing = (
                a.housing
                and a.housing.experiment == intent.design
                and a.housing.experiment_steps > 0
                and a.housing.studying_id is None
            )
            if not ongoing and not affordable(
                prototype_cost(intent.design), materials(world, a, a.position)
            ):
                return "Insufficient prototype materials"
    elif intent.action in (Action.STORE, Action.WITHDRAW):
        s = storage_access(world, a)
        if s is None:
            return "Shared storage must be within two tiles"
        if intent.assembly_design is not None:
            from app.simulation.engineering.assemblies import cost, design_id

            if (
                intent.action != Action.WITHDRAW
                or not a.workshop
                or not any(
                    design_id(t.design) == design_id(intent.assembly_design)
                    for t in a.workshop.trials
                )
                or intent.item not in cost(intent.assembly_design)
            ):
                return "Device supplies require a personally tested assembly plan"
        if intent.item not in RESOURCE_KINDS:
            return "Unsupported storage item"
        source, destination = (
            (a.inventory, s.storage) if intent.action == Action.STORE else (s.storage, a.inventory)
        )
        if getattr(source, intent.item) < intent.amount:
            return "Storage transfer lacks requested quantity"
        room = (
            carrying_room(destination, intent.item, communal=intent.action == Action.STORE)
            if world.config.infinite
            else destination.capacity - destination.total
        )
        if intent.amount > room:
            return "Storage destination is full"
    elif intent.action == Action.CRAFT:
        if a.energy < 3:
            return "Not enough energy for crafting"
        if intent.item not in TOOL_COSTS:
            return "Unsupported tool recipe"
        if a.inventory.tools.get(intent.item, 0) > 0:
            return "Tool already equipped"
        if a.inventory.total >= a.inventory.capacity:
            return "Inventory is full"
        benches = [
            b
            for b in world.buildings.values()
            if b.kind == "workbench" and building_usable(b) and b.position.distance(a.position) <= 1
        ]
        if not benches:
            return "Crafting requires a nearby completed workbench"
        if not affordable(TOOL_COSTS[intent.item], materials(world, a, a.position)):
            return "Insufficient crafting materials"
    elif intent.action == Action.REFUEL:
        b = world.buildings.get(intent.building_id or "")
        if (
            not b
            or b.kind != "campfire"
            or b.position.distance(a.position) > 1
            or not building_usable(b)
        ):
            return "Completed campfire must be within one tile"
        if b.fuel >= 96:
            return "Campfire fuel is full"
        if not affordable({"fuel": 1}, materials(world, a, b.position)):
            return "No fuel available"
    elif intent.action == Action.BUILD:
        if world.ecosystem and any(
            c.position == intent.target for c in world.ecosystem.crops.values()
        ):
            return "Cannot build over a planted crop"
        if intent.building_kind not in BUILD_COSTS:
            return "Unsupported building recipe"
        if intent.target is None or a.position.distance(intent.target) > 1:
            return "Build site must be within one tile"
        if a.energy < 4:
            return "Not enough energy for construction"
        tile = access.tile(intent.target)
        if tile is None:
            return "Invalid build site"
        b = next((b for b in world.buildings.values() if b.position == intent.target), None)
        design = (
            b.design if b and b.design and b.durability > 0 else (intent.design or best_design(a))
        )
        if intent.building_kind in HOUSING:
            if design is None or not tested(a, design):
                return "No tested shelter design; experiment or study before building"
        cost = construction_cost(intent.building_kind, design)
        if intent.building_kind in ("wooden_wall", "stone_wall", "watchtower"):
            if any(v.alive and v.position == intent.target for v in world.agents.values()):
                return "Cannot build an obstacle on an agent"
        if b:
            if b.kind != intent.building_kind or (b.progress == 100 and b.durability > 0):
                return "Build site already occupied by a structure"
            if b.durability == 0 and not affordable(cost, materials(world, a, intent.target)):
                return "Insufficient reconstruction materials"
        else:
            if intent.building_kind == "bridge":
                if tile.terrain.value != "water":
                    return "Bridges require a water tile"
            elif not tile.walkable:
                return "Build site is not walkable"
            if intent.building_kind == "farm" and tile.terrain.value not in ("soil", "grass"):
                return "Farm requires fertile soil or grass"
            if not affordable(cost, materials(world, a, intent.target)):
                return "Insufficient construction materials"
    return None


def resolve_construction(world, intent, access) -> str:
    a = world.agents[intent.actor_id]
    if intent.action == Action.EXPERIMENT_TOOL or (
        intent.action == Action.CRAFT and world.config.infinite
    ):
        from app.simulation.engineering.invention import resolve

        return resolve(world, a, intent)
    if intent.action == Action.EXPERIMENT:
        from app.simulation.engineering.housing import experiment

        return experiment(world, a, intent)
    if intent.action in (Action.STORE, Action.WITHDRAW):
        s = storage_access(world, a)
        source, destination = (
            (a.inventory, s.storage) if intent.action == Action.STORE else (s.storage, a.inventory)
        )
        setattr(source, intent.item, getattr(source, intent.item) - intent.amount)
        setattr(destination, intent.item, getattr(destination, intent.item) + intent.amount)
        if intent.assembly_design is not None:
            a.workshop.planned = intent.assembly_design.model_copy(deep=True)
        verb = "stored" if intent.action == Action.STORE else "withdrew"
        return f"{a.name} {verb} {intent.amount} {intent.item}"
    if intent.action == Action.CRAFT:
        pay(TOOL_COSTS[intent.item], materials(world, a, a.position))
        a.inventory.tools[intent.item] = 80
        a.energy = max(0, a.energy - 3)
        return f"{a.name} crafted a {intent.item}"
    if intent.action == Action.REFUEL:
        b = world.buildings[intent.building_id]
        pay({"fuel": 1}, materials(world, a, b.position))
        b.fuel += 4
        return f"{a.name} refueled the campfire"
    b = next((b for b in world.buildings.values() if b.position == intent.target), None)
    design = (intent.design or best_design(a)) if intent.building_kind in HOUSING else None
    if b is None:
        pay(construction_cost(intent.building_kind, design), materials(world, a, intent.target))
        key = f"building:{intent.target.x}:{intent.target.y}"
        b = Building(
            id=key,
            kind=intent.building_kind,
            position=intent.target.model_copy(),
            settlement_id=a.settlement_id if intent.building_kind != "remote_camp" else None,
            owner_id=a.id,
            created_tick=world.tick + 1,
        )
        if design is not None:
            b.design, b.quality = design.model_copy(), 0
        world.buildings[key] = b
        if b.settlement_id in world.settlements:
            world.settlements[b.settlement_id].buildings.append(key)
    elif b.durability == 0:
        pay(construction_cost(b.kind, design), materials(world, a, b.position))
        b.progress, b.durability = 0, 100
        b.fuel = 0
        if design is not None:
            b.design, b.quality, b.work_units, b.contributors = design.model_copy(), 0, 0, []
            b.last_damage_cause = ""
            b.last_damage_tick = 0
    if b.kind in HOUSING and b.design is None and design is not None:
        b.design, b.quality = design.model_copy(), 0
    if b.design is not None:
        k = knowledge(a)
        quality = workmanship(a, b.design, world.config.seed, world.tick + 1, f"building:{b.id}")
        b.quality = round((b.quality * b.work_units + quality) / (b.work_units + 1), 4)
        b.work_units += 1
        if a.id not in b.contributors:
            b.contributors = [*b.contributors, a.id][-30:]
        k.practice += 2
    b.progress = min(100, b.progress + 25)
    a.energy = max(0, a.energy - 4)
    if b.progress == 100 and b.design is not None:
        b.durability = round(35 + b.quality * 65)
    if b.kind == "campfire" and b.progress == 100:
        b.fuel = 4
    if b.kind == "remote_camp" and b.progress == 100:
        # Permanent migration is optional and conditional on traits plus actual time away.
        t = a.personality
        if t.independence > 0.72 and t.loyalty < 0.35 and a.time_away > 120:
            if a.settlement_id in world.settlements:
                world.settlements[a.settlement_id].members.remove(a.id)
            a.settlement_id = None
            a.lifestyle = "wanderer"
            a.home = b.position.model_copy()
            a.time_away = 0
    verb = "completed" if b.progress == 100 else "worked on"
    quality_note = f", workmanship {b.quality:.0%}" if b.design else ""
    return f"{a.name} {verb} {b.kind.replace('_', ' ')} ({b.progress}%{quality_note})"
