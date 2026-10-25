"""Experiments, fabricated devices, finite production and consensual barter."""

from app.simulation.chunks.access import recovered_quantity
from app.simulation.cognition.tiers import retain
from app.simulation.engineering.assemblies import (
    PRODUCTS,
    change,
    cost,
    design_id,
    evaluate,
    knowledge,
    quantity,
)
from app.simulation.models.domain import (
    RESOURCE_KINDS,
    Action,
    AssemblyTrial,
    Building,
    MemoryRecord,
    ResourceModification,
)
from app.simulation.settlements.effects import building_usable

WORKSHOP_ACTIONS = (
    Action.EXPERIMENT_ASSEMBLY,
    Action.ASSEMBLE,
    Action.OPERATE,
    Action.HEAT,
    Action.DISMANTLE,
    Action.OFFER_TRADE,
    Action.ACCEPT_TRADE,
)
ITEMS = (*RESOURCE_KINDS, *PRODUCTS)


def sources(world, a):
    from app.simulation.actions.construction import storage_access

    s = storage_access(world, a)
    return [a.inventory, s.storage] if s else [a.inventory]


def affordable(c, inventories):
    return all(sum(quantity(inv, m) for inv in inventories) >= n for m, n in c.items())


def pay(c, inventories):
    for m, n in c.items():
        for inv in inventories:
            take = min(n, quantity(inv, m))
            if take:
                change(inv, m, -take)
            n -= take


def fisheries(world, p):
    # All devices on one 8x8 water patch compete for the same slowly recovering stock.
    key = f"fish:{p.x // 8}:{p.y // 8}:food"
    m = world.resource_modifications.get(key)
    stock = (
        recovered_quantity(
            m.quantity, 4, m.tick, world.tick, world.config.regeneration_ticks, "food"
        )
        if m
        else 4
    )
    return key, stock


def heat_level(b):
    return b.assembly.measured.get("heat", 0) if b.assembly else 0.35 if b.kind == "campfire" else 0


def trade_problem(world, a, offer, peer):
    if not peer or not peer.alive or peer.id == a.id or a.position.distance(peer.position) > 1:
        return "Barter requires a living adjacent partner"
    if offer.give_item not in ITEMS or offer.want_item not in ITEMS:
        return "Unsupported barter item"
    if offer.give_item == offer.want_item:
        return "Barter requires different items"
    if quantity(a.inventory, offer.give_item) < offer.give_amount:
        return "Offering actor no longer has the promised goods"
    return None


def validate(world, intent, access):
    a = world.agents[intent.actor_id]
    if not world.config.infinite:
        return "Workshop actions require a modern world"
    if intent.action == Action.OFFER_TRADE:
        offer = intent.trade
        if offer is None or offer.peer_id != intent.peer_id:
            return "A barter proposal must name its intended partner"
        if not world.tick < offer.expires <= world.tick + 120:
            return "Barter offers expire within 120 ticks"
        return trade_problem(world, a, offer, world.agents.get(intent.peer_id or ""))
    if intent.action == Action.ACCEPT_TRADE:
        maker = world.agents.get(intent.peer_id or "")
        offer = maker.workshop.offer if maker and maker.workshop else None
        if (
            not offer
            or offer.id != intent.item
            or offer.peer_id != a.id
            or offer.expires <= world.tick
        ):
            return "No matching live offer addressed to this actor"
        problem = trade_problem(world, maker, offer, a)
        if problem:
            return problem
        if quantity(a.inventory, offer.want_item) < offer.want_amount:
            return "Accepting actor lacks the requested goods"
        if (
            a.inventory.total - offer.want_amount + offer.give_amount > a.inventory.capacity
            or maker.inventory.total - offer.give_amount + offer.want_amount
            > maker.inventory.capacity
        ):
            return "Barter would exceed an inventory capacity"
        return None
    if a.energy < 6:
        return "Recover energy before workshop work"
    if intent.action in (Action.EXPERIMENT_ASSEMBLY, Action.ASSEMBLE):
        d = intent.assembly_design
        if d is None:
            return "A physical assembly hypothesis is required"
        k = a.workshop
        ongoing = (
            k and k.experiment is not None and design_id(k.experiment) == design_id(d) and k.steps
        )
        if intent.action == Action.EXPERIMENT_ASSEMBLY:
            if intent.building_id:
                b = world.buildings.get(intent.building_id)
                if (
                    not b
                    or not b.assembly
                    or not building_usable(b)
                    or a.position.distance(b.position) > 1
                ):
                    return "Study requires an adjacent working real device"
                if design_id(b.assembly.design) != design_id(d):
                    return "Study design differs from the observable device"
            if ongoing:
                return None
        else:
            if not k or not any(
                design_id(t.design) == design_id(d) and max(t.measured.values()) >= 0.3
                for t in k.trials
            ):
                return "Experiment or study personally before fabricating a device"
            if intent.target is None or a.position.distance(intent.target) > 1:
                return "Fabrication site must be within one tile"
            if world.ecosystem and any(
                c.position == intent.target for c in world.ecosystem.crops.values()
            ):
                return "Cannot fabricate over a planted crop"
            tile = access.tile(intent.target)
            if tile is None or not tile.walkable:
                return "Fabrication requires accessible land"
            if any(b.position == intent.target for b in world.buildings.values()):
                return "Fabrication site already contains a structure or ruin"
            if any(
                p.alive and p.id != a.id and p.position == intent.target
                for p in world.agents.values()
            ):
                return "Fabrication site is occupied"
            if any(r.position == intent.target for r in access.visible_resources(intent.target, 0)):
                return "Fabrication cannot cover a natural resource node"
        if not affordable(cost(d), sources(world, a)):
            return "Insufficient local materials for the assembly"
        return None
    b = world.buildings.get(intent.building_id or "")
    if not b or a.position.distance(b.position) > 1:
        return "Device must be within one tile"
    if intent.action == Action.DISMANTLE:
        if b.owner_id != a.id or b.salvaged:
            return "Only the owner can salvage a structure once"
        if not b.assembly:
            return "Only experimental devices support material recovery"
        recovered = {m: n // 2 for m, n in cost(b.assembly.design).items()}
        if a.inventory.total + sum(recovered.values()) > a.inventory.capacity:
            return "No carrying room for recovered materials"
        return None
    if not building_usable(b):
        return "Device is unfinished or broken"
    if intent.action == Action.HEAT:
        if intent.item not in ("food", "wood", "clay", "ore"):
            return "Choose a carried material for a heating trial"
        if quantity(a.inventory, intent.item) < 1:
            return "No carried input for heating"
        if heat_level(b) <= 0:
            return "This device has no measured heating effect"
        if b.kind == "campfire":
            if b.fuel < 1:
                return "Fire needs fuel"
        elif a.inventory.fuel < 1:
            return "Heating the chamber requires carried fuel"
        # Wood carbonization produces two fuel units; all other transformations replace one item.
        projected = a.inventory.total + (1 if intent.item == "wood" else 0) - (b.kind != "campfire")
        if projected > a.inventory.capacity:
            return "No room for the possible heating output"
        return None
    if not b.assembly or intent.item not in ("catch", "water", "cultivate"):
        return "Choose an operation supported by a tested physical assembly"
    if b.assembly.measured.get(intent.item, 0) < 0.3:
        return "The device did not demonstrate enough performance for this operation"
    wait = 120 if intent.item == "cultivate" else 24 if intent.item == "catch" else 8
    if world.tick - b.last_operated_tick < wait:
        return "Device needs time before another production cycle"
    if intent.item in ("catch", "water"):
        target = intent.target
        tile = access.tile(target) if target else None
        if tile is None or tile.terrain.value != "water" or b.position.distance(target) > 1:
            return "Operation requires water immediately beside the device"
        if a.inventory.total >= a.inventory.capacity:
            return "No carrying room for production"
        if intent.item == "catch" and fisheries(world, target)[1] < 1:
            return "This water patch is depleted; allow recovery or move"
    else:
        farms = [
            v
            for v in world.buildings.values()
            if v.kind == "farm" and building_usable(v) and v.position.distance(b.position) <= 1
        ]
        if not farms or a.inventory.seeds < 1 or a.inventory.water < 1:
            return "Cultivation needs an adjacent working farm, one seed and one water"
    return None


def remember(a, world, text, outcome=0.5):
    retain(
        a,
        MemoryRecord(
            id=f"workshop:{a.id}:{world.tick + 1}",
            tick=world.tick + 1,
            kind="reflection",
            text=text[:500],
            goal="experiment_assembly",
            outcome=outcome,
            importance=0.85,
            position=a.position.model_copy(),
        ),
    )


def resolve(world, intent, access):
    a = world.agents[intent.actor_id]
    k = knowledge(a)
    if intent.action == Action.OFFER_TRADE:
        k.offer = intent.trade.model_copy(deep=True)
        return (
            f"{a.name} offered {k.offer.give_amount} {k.offer.give_item} "
            f"for {k.offer.want_amount} {k.offer.want_item}"
        )
    if intent.action == Action.ACCEPT_TRADE:
        maker = world.agents[intent.peer_id]
        o = maker.workshop.offer
        change(maker.inventory, o.give_item, -o.give_amount)
        change(a.inventory, o.give_item, o.give_amount)
        change(a.inventory, o.want_item, -o.want_amount)
        change(maker.inventory, o.want_item, o.want_amount)
        maker.workshop.offer = None
        text = (
            f"{a.name} and {maker.name} bartered {o.give_amount} {o.give_item} "
            f"for {o.want_amount} {o.want_item}"
        )
        for person, peer in ((a, maker), (maker, a)):
            person.relationships[peer.id] = min(1, person.relationships.get(peer.id, 0.5) + 0.04)
            remember(person, world, text)
        return text
    a.energy -= 6
    if intent.action == Action.EXPERIMENT_ASSEMBLY:
        d = intent.assembly_design
        ongoing = k.experiment and design_id(k.experiment) == design_id(d) and k.steps
        if not ongoing:
            pay(cost(d), sources(world, a))
            k.experiment, k.steps = d.model_copy(deep=True), 0
        if k.steps < 2:
            k.steps += 1
            return f"{a.name} tested {d.name}: {k.steps}/3"
        measured, feedback = evaluate(d)
        t = AssemblyTrial(
            design=d.model_copy(deep=True),
            tick=world.tick + 1,
            measured=measured,
            feedback=feedback,
            source="study" if intent.building_id else "experiment",
        )
        k.trials = [*k.trials, t][-24:]
        k.experiment, k.steps = None, 0
        text = f"{a.name} tested {d.name}: " + "; ".join(feedback)
        remember(a, world, text, 0.6 if max(measured.values()) >= 0.3 else -0.3)
        return text
    if intent.action == Action.ASSEMBLE:
        d = intent.assembly_design
        trial = next(t for t in reversed(k.trials) if design_id(t.design) == design_id(d))
        pay(cost(d), sources(world, a))
        key = f"building:{intent.target.x}:{intent.target.y}"
        b = Building(
            id=key,
            kind="assembly",
            position=intent.target.model_copy(),
            owner_id=a.id,
            settlement_id=a.settlement_id,
            progress=100,
            created_tick=world.tick + 1,
            assembly=trial.model_copy(deep=True),
            contributors=[a.id],
            quality=max(trial.measured.values()),
        )
        world.buildings[key] = b
        k.planned = None
        if a.settlement_id in world.settlements:
            world.settlements[a.settlement_id].buildings.append(key)
        return f"{a.name} fabricated {d.name} at ({b.position.x}, {b.position.y})"
    b = world.buildings[intent.building_id]
    if intent.action == Action.DISMANTLE:
        for m, n in cost(b.assembly.design).items():
            if n // 2:
                change(a.inventory, m, n // 2)
        b.salvaged, b.progress, b.durability = True, 0, 0
        return f"{a.name} dismantled {b.assembly.design.name} and recovered some materials"
    if intent.action == Action.HEAT:
        level = heat_level(b)
        if b.kind == "campfire":
            b.fuel -= 1
        else:
            a.inventory.fuel -= 1
        change(a.inventory, intent.item, -1)
        output, needed = {
            "food": ("cooked_food", 0.2),
            "wood": ("fuel", 0.25),
            "clay": ("ceramic", 0.55),
            "ore": ("metal", 0.7),
        }[intent.item]
        success = level >= needed
        if success:
            change(a.inventory, output, 2 if output == "fuel" else 1)
        key = f"{intent.item}:{'hot' if level >= 0.7 else 'warm' if level >= 0.55 else 'low'}"
        lessons = k.transformations | {key: output if success else "input lost; insufficient heat"}
        k.transformations = dict(list(lessons.items())[-16:])
        if (
            b.assembly
            and b.assembly.design.mechanism == "combustion"
            and any(p.material in ("wood", "fiber") for p in b.assembly.design.parts)
        ):
            b.durability = max(0, b.durability - 15)
        result = "produced " + output if success else "trial failed; input lost"
        text = f"{a.name} heated {intent.item}: {result}"
        remember(a, world, text, 0.5 if success else -0.3)
        return text
    b.last_operated_tick = world.tick
    if intent.item == "catch":
        key, stock = fisheries(world, intent.target)
        world.resource_modifications[key] = ResourceModification(
            quantity=stock - 1, tick=world.tick, capacity=4
        )
        a.inventory.food += 1
        b.food += 1
        text = f"{a.name} caught food with {b.assembly.design.name}"
    elif intent.item == "water":
        a.inventory.water += 1
        text = f"{a.name} collected water with {b.assembly.design.name}"
    else:
        a.inventory.seeds -= 1
        a.inventory.water -= 1
        a.inventory.food += 2
        b.food += 2
        text = f"{a.name} cultivated two meals with {b.assembly.design.name}"
    b.durability = max(0, b.durability - 1)
    return text
