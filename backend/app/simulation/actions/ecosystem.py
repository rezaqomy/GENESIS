"""Authoritative farming, husbandry, conflict and dropped-item transfers."""

import hashlib

from app.simulation.ecology.environment import drop_inventory, living
from app.simulation.engineering.assemblies import change
from app.simulation.engineering.invention import best_tool
from app.simulation.models.domain import (
    RESOURCE_KINDS,
    Action,
    Animal,
    CombatState,
    Crop,
    Episode,
    Inventory,
    Terrain,
    Tile,
)

ECO_ACTIONS = {
    Action.TILL,
    Action.PLANT,
    Action.WATER_CROP,
    Action.HARVEST,
    Action.FEED,
    Action.BREED,
    Action.COLLECT,
    Action.ATTACK,
    Action.STEAL,
    Action.PICK_UP,
}
CROP_ACTIONS = {Action.TILL, Action.PLANT, Action.WATER_CROP, Action.HARVEST}
ANIMAL_ACTIONS = {Action.FEED, Action.BREED, Action.COLLECT}


def crop_key(p):
    return f"crop:{p.x},{p.y}"


def count_item(inventory, item):
    if item in inventory.tools:
        return int(inventory.tools[item] > 0)
    if item in RESOURCE_KINDS:
        return getattr(inventory, item)
    return inventory.products.get(item, 0)


def transfer(source, receiver, item, amount):
    if item in source.tools:
        receiver.tools[item] = source.tools[item]
        del source.tools[item]
    elif item in RESOURCE_KINDS:
        change(source, item, -amount)
        change(receiver, item, amount)
    else:
        source.products = source.products | {item: source.products[item] - amount}
        receiver.products = receiver.products | {item: receiver.products.get(item, 0) + amount}


def validate(world, intent, access):
    a = world.agents[intent.actor_id]
    e = world.ecosystem
    if not world.config.infinite:
        return "Living systems require a modern world"
    if a.energy < 6:
        return "Not enough energy"
    if intent.action in CROP_ACTIONS:
        p = intent.target
        if p is None or a.position.distance(p) > 1:
            return "Crop work must be within one tile"
        tile = access.tile(p)
        if tile is None or not tile.walkable:
            return "Crop work needs accessible land"
        crop = e.crops.get(crop_key(p)) if e else None
        if intent.action in (Action.TILL, Action.PLANT):
            if crop or any(b.position == p for b in world.buildings.values()):
                return "The ground is occupied by a crop or structure"
            if any(r.position == p for r in access.visible_resources(p, 0)):
                return "Natural resource nodes cannot be replaced with crops"
            if intent.action == Action.TILL:
                if tile.terrain != Terrain.GRASS:
                    return "Only intact grass can be tilled; extracted paths need carried soil"
            elif tile.terrain != Terrain.SOIL or a.inventory.seeds < 1:
                return "Planting requires soil and a carried seed"
            if intent.action == Action.PLANT and e and len(e.crops) >= 128:
                return "Crop population budget reached"
        else:
            if crop is None:
                return "No crop at the target"
            if intent.action == Action.WATER_CROP:
                if crop.health == 0 or crop.moisture > 60 or a.inventory.water < 1:
                    return "Watering needs a thirsty living crop and carried water"
            elif crop.health and crop.growth < 80:
                return "This crop has not ripened"
            elif crop.health and a.inventory.capacity - a.inventory.total < 5:
                return "Harvest needs room for three food and two seeds"
        return None
    if intent.action in ANIMAL_ACTIONS or (
        intent.action == Action.ATTACK and intent.entity_id is not None
    ):
        animal = e.animals.get(intent.entity_id) if e else None
        if animal is None or animal.health == 0 or a.position.distance(animal.position) > 1:
            return "A living animal must be within one tile"
        if intent.action == Action.FEED:
            if a.inventory.seeds < 1:
                return "Feeding requires a carried seed"
            if animal.owner_id not in (None, a.id):
                return "Cannot claim someone else's animal by feeding it"
            if animal.hunger < 10 and animal.ready_until >= world.tick:
                return "This animal has already been fed"
        elif intent.action == Action.BREED:
            mate = e.animals.get(intent.resource_id or "")
            if len(e.animals) >= 96 or len(e.drops) >= 128:
                return "Animal population budget reached"
            if (
                mate is None
                or mate.id == animal.id
                or mate.species != animal.species
                or mate.position.distance(animal.position) > 2
                or a.position.distance(mate.position) > 2
                or any(
                    v.owner_id != a.id
                    or v.hunger > 40
                    or v.ready_until < world.tick
                    or v.breed_after > world.tick
                    or world.tick - v.born_tick < 240
                    for v in (animal, mate)
                )
            ):
                return "Breeding needs two nearby, tame, fed adults off cooldown"
        elif intent.action == Action.COLLECT:
            item = "fiber" if animal.species == "sheep" else "food"
            if animal.owner_id != a.id or animal.produce_after > world.tick:
                return "Animal must be yours and ready to produce"
            if animal.hunger > 40 or world.tick - animal.born_tick < 240:
                return "Only a fed adult produces supplies"
            if a.inventory.total >= a.inventory.capacity:
                return f"No carrying room for {item}"
            if animal.species == "sheep" and best_tool(a, "cut")[1] < 0.3:
                return "Shearing needs a personally tested cutting tool"
        # ATTACK proceeds through the same cooldown checks as interpersonal combat.
        if intent.action != Action.ATTACK:
            return None
    elif intent.action in (Action.ATTACK, Action.STEAL):
        peer = world.agents.get(intent.peer_id or "")
        if peer is None or not peer.alive or peer.id == a.id:
            return "A distinct living peer is required"
        if a.position.distance(peer.position) > 1:
            return "Peer must be within one tile"
        if intent.action == Action.STEAL:
            if intent.item not in RESOURCE_KINDS:
                return "Only basic carried supplies can be stolen"
            if count_item(peer.inventory, intent.item) < intent.amount:
                return "The peer no longer carries enough of that item"
            if a.inventory.total + intent.amount > a.inventory.capacity:
                return "No carrying room for stolen supplies"
            return None
    elif intent.action == Action.PICK_UP:
        drop = e.drops.get(intent.entity_id or "") if e else None
        if drop is None or drop.expires <= world.tick:
            return "No unexpired dropped belongings"
        if a.position.distance(drop.position) > 1:
            return "Dropped belongings must be within one tile"
        if not intent.item or count_item(drop.inventory, intent.item) < intent.amount:
            return "Not enough of that dropped item"
        if intent.item in drop.inventory.tools and (
            intent.amount != 1 or a.inventory.tools.get(intent.item, 0) > 0
        ):
            return "Pick up one tool into an empty tool slot"
        if a.inventory.total + intent.amount > a.inventory.capacity:
            return "No carrying room for dropped items"
        return None
    if intent.action == Action.ATTACK:
        if a.combat and world.tick - a.combat.last_attack_tick < 8:
            return "Recover before attacking again"
        return None
    return "Unknown ecosystem action"


def offense(world, attacker, victim, text):
    victim.relationships[attacker.id] = max(-1, victim.relationships.get(attacker.id, 0) - 0.5)
    victim.psychology.fear = min(1, victim.psychology.fear + 0.2)
    victim.memories = [
        *victim.memories,
        Episode(tick=world.tick, kind="conflict", text=text, outcome=-1, peer_id=attacker.id),
    ][-48:]
    for witness in world.agents.values():
        if (
            witness.alive
            and witness.id not in (attacker.id, victim.id)
            and witness.position.distance(victim.position) <= witness.vision_radius
        ):
            witness.relationships[attacker.id] = max(
                -1, witness.relationships.get(attacker.id, 0) - 0.18
            )


def resolve(world, intent, access):
    a, e = world.agents[intent.actor_id], living(world)
    a.energy -= 6
    if intent.action in CROP_ACTIONS:
        p, key = intent.target, crop_key(intent.target)
        if intent.action == Action.TILL:
            world.terrain_modifications[f"{p.x},{p.y}"] = Tile(
                position=p.model_copy(), terrain=Terrain.SOIL, walkable=True
            )
            return f"{a.name} tilled soil at ({p.x}, {p.y})"
        if intent.action == Action.PLANT:
            a.inventory.seeds -= 1
            e.crops[key] = Crop(
                id=key, position=p.model_copy(), owner_id=a.id, planted_tick=world.tick + 1
            )
            return f"{a.name} planted a seed at ({p.x}, {p.y})"
        crop = e.crops[key]
        if intent.action == Action.WATER_CROP:
            a.inventory.water -= 1
            crop.moisture = min(100, crop.moisture + 40)
            return f"{a.name} watered a growing crop"
        if crop.health:
            a.inventory.food += 3
            a.inventory.seeds += 2
            owner = world.agents.get(crop.owner_id)
            if owner and owner.id != a.id:
                offense(world, a, owner, f"{a.name} harvested my crop without asking")
        del e.crops[key]
        return f"{a.name} {'harvested food and seeds' if crop.health else 'cleared a dead crop'}"
    if intent.action in ANIMAL_ACTIONS:
        animal = e.animals[intent.entity_id]
        if intent.action == Action.FEED:
            a.inventory.seeds -= 1
            animal.hunger = max(0, animal.hunger - 25)
            if animal.tamer_id != a.id:
                animal.trust = 0
                animal.tamer_id = a.id
            animal.trust = min(3, animal.trust + 1)
            if animal.trust == 3:
                animal.owner_id = a.id
            animal.ready_until = world.tick + 120
            return f"{a.name} fed a {animal.species}; trust {animal.trust}/3"
        if intent.action == Action.BREED:
            mate = e.animals[intent.resource_id]
            signature = f"{world.tick}:{animal.id}:{mate.id}".encode()
            identifier = "offspring:" + hashlib.sha256(signature).hexdigest()[:20]
            child = Animal(
                id=identifier,
                species=animal.species,
                position=animal.position.model_copy(),
                born_tick=world.tick + 1,
                owner_id=a.id,
                trust=3,
                tamer_id=a.id,
                produce_after=world.tick + 240,
            )
            e.animals[child.id] = child
            for v in (animal, mate):
                v.ready_until = -1
                v.breed_after = world.tick + 480
                v.hunger = min(100, v.hunger + 20)
            return f"{a.name} bred two {animal.species}; a juvenile was born"
        item = "fiber" if animal.species == "sheep" else "food"
        change(a.inventory, item, 1)
        animal.hunger = min(100, animal.hunger + 15)
        animal.produce_after = world.tick + 240
        if animal.species == "sheep":
            tool, _ = best_tool(a, "cut")
            a.inventory.tools[tool] -= 1
        return f"{a.name} collected {item} from a tame {animal.species}"
    if intent.action == Action.PICK_UP:
        drop = e.drops[intent.entity_id]
        transfer(drop.inventory, a.inventory, intent.item, intent.amount)
        if drop.inventory.total == 0:
            del e.drops[drop.id]
        return f"{a.name} picked up {intent.amount} {intent.item}"
    peer = world.agents.get(intent.peer_id or "")
    if intent.action == Action.STEAL:
        transfer(peer.inventory, a.inventory, intent.item, intent.amount)
        offense(world, a, peer, f"{a.name} stole {intent.amount} {intent.item} from me")
        return f"{a.name} stole {intent.amount} {intent.item} from {peer.name}"
    if a.combat is None:
        a.combat = CombatState()
    a.combat.last_attack_tick = world.tick
    tool, cutting = best_tool(a, "cut")
    damage = 4 + int(cutting * 10)
    if tool and cutting > 0:
        a.inventory.tools[tool] -= 1
    if intent.entity_id:
        animal = e.animals[intent.entity_id]
        animal.health = max(0, animal.health - damage)
        animal.frightened_until = world.tick + 48
        owner = world.agents.get(animal.owner_id or "")
        if owner and owner.id != a.id:
            offense(world, a, owner, f"{a.name} attacked my {animal.species}")
        if animal.health == 0:
            drop_inventory(
                world,
                f"carcass:{animal.id}:{world.tick}",
                animal.position,
                Inventory(food=2),
                world.tick,
            )
            del e.animals[animal.id]
        return f"{a.name} hit a {animal.species} for {damage} damage"
    if peer.combat is None:
        peer.combat = CombatState()
    peer.combat.attacker_id, peer.combat.attacked_tick = a.id, world.tick
    peer.health = max(0, peer.health - damage)
    offense(world, a, peer, f"{a.name} attacked me for {damage} damage")
    if peer.health == 0:
        peer.alive = False
        peer.current_action = Action.IDLE
        peer.destination = None
        peer.combat.death_cause = f"killed by {a.name}"
    return f"{a.name} hit {peer.name} for {damage} damage"
