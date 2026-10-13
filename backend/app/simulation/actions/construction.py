from app.simulation.models.domain import RESOURCE_KINDS, Action, Building, WorldState
from app.simulation.settlements.effects import BUILD_COSTS, TOOL_COSTS


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
        and world.buildings[k].progress == 100
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
    if intent.action in (Action.STORE, Action.WITHDRAW):
        s = storage_access(world, a)
        if s is None:
            return "Shared storage must be within two tiles"
        if intent.item not in RESOURCE_KINDS:
            return "Unsupported storage item"
        source, destination = (
            (a.inventory, s.storage) if intent.action == Action.STORE else (s.storage, a.inventory)
        )
        if getattr(source, intent.item) < intent.amount:
            return "Storage transfer lacks requested quantity"
        if destination.total + intent.amount > destination.capacity:
            return "Storage destination is full"
    elif intent.action == Action.CRAFT:
        if intent.item not in TOOL_COSTS:
            return "Unsupported tool recipe"
        if a.inventory.tools.get(intent.item, 0) > 0:
            return "Tool already equipped"
        if a.inventory.total >= a.inventory.capacity:
            return "Inventory is full"
        benches = [
            b
            for b in world.buildings.values()
            if b.kind == "workbench"
            and b.progress == 100
            and b.durability > 0
            and b.position.distance(a.position) <= 1
        ]
        if not benches:
            return "Crafting requires a nearby completed workbench"
        if not affordable(TOOL_COSTS[intent.item], materials(world, a, a.position)):
            return "Insufficient crafting materials"
    elif intent.action == Action.REFUEL:
        b = world.buildings.get(intent.building_id or "")
        if not b or b.kind != "campfire" or b.position.distance(a.position) > 1 or b.progress < 100:
            return "Completed campfire must be within one tile"
        if b.fuel >= 96:
            return "Campfire fuel is full"
        if not affordable({"fuel": 1}, materials(world, a, b.position)):
            return "No fuel available"
    elif intent.action == Action.BUILD:
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
        if b:
            if b.kind != intent.building_kind or b.progress == 100:
                return "Build site already occupied by a structure"
        else:
            if intent.building_kind == "bridge":
                if tile.terrain.value != "water":
                    return "Bridges require a water tile"
            elif not tile.walkable:
                return "Build site is not walkable"
            if intent.building_kind == "farm" and tile.terrain.value not in ("soil", "grass"):
                return "Farm requires fertile soil or grass"
            if intent.building_kind in ("wooden_wall", "stone_wall", "watchtower"):
                if any(v.alive and v.position == intent.target for v in world.agents.values()):
                    return "Cannot build an obstacle on an agent"
            if not affordable(
                BUILD_COSTS[intent.building_kind], materials(world, a, intent.target)
            ):
                return "Insufficient construction materials"
    return None


def resolve_construction(world, intent, access) -> str:
    a = world.agents[intent.actor_id]
    if intent.action in (Action.STORE, Action.WITHDRAW):
        s = storage_access(world, a)
        source, destination = (
            (a.inventory, s.storage) if intent.action == Action.STORE else (s.storage, a.inventory)
        )
        setattr(source, intent.item, getattr(source, intent.item) - intent.amount)
        setattr(destination, intent.item, getattr(destination, intent.item) + intent.amount)
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
    if b is None:
        pay(BUILD_COSTS[intent.building_kind], materials(world, a, intent.target))
        key = f"building:{intent.target.x}:{intent.target.y}"
        b = Building(
            id=key,
            kind=intent.building_kind,
            position=intent.target.model_copy(),
            settlement_id=a.settlement_id if intent.building_kind != "remote_camp" else None,
            owner_id=a.id,
            created_tick=world.tick + 1,
        )
        world.buildings[key] = b
        if b.settlement_id in world.settlements:
            world.settlements[b.settlement_id].buildings.append(key)
    b.progress = min(100, b.progress + 25)
    a.energy = max(0, a.energy - 4)
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
    return f"{a.name} {verb} {b.kind.replace('_', ' ')} ({b.progress}%)"
