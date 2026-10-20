from app.simulation.chunks.generator import sample
from app.simulation.models.domain import (
    Animal,
    DroppedItems,
    Ecosystem,
    Inventory,
    Position,
    Terrain,
)


def living(world):
    if world.ecosystem is None:
        world.ecosystem = Ecosystem()
    return world.ecosystem


def wet_near(access, position):
    return any(
        (tile := access.tile(Position(x=position.x + dx, y=position.y + dy)))
        and tile.terrain == Terrain.WATER
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0), (0, 2), (0, -2), (2, 0), (-2, 0))
    )


def drop_inventory(world, identifier, position, inventory, tick, owner=None):
    if inventory.total == 0:
        return
    e = living(world)
    e.drops[identifier] = DroppedItems(
        id=identifier,
        position=position.model_copy(),
        inventory=inventory.model_copy(deep=True),
        expires=tick + 1200,
        owner_id=owner,
    )


def release_dead(world, tick):
    """Runs for every cause of death, once; retains tool durability and refined items."""
    e = living(world)
    messages = []
    for a in world.agents.values():
        if not a.alive and a.id not in e.released_agents:
            drop_inventory(world, f"grave:{a.id}", a.position, a.inventory, tick, a.id)
            a.inventory = Inventory(capacity=a.inventory.capacity)
            e.released_agents.append(a.id)
            messages.append(
                ("ITEMS_DROPPED", {"message": f"{a.name}'s belongings fell to the ground"})
            )
    return messages


def advance_ecology(world, access, tick, weather):
    e = living(world)
    messages = []
    for key in list(e.drops):
        if e.drops[key].expires <= tick:
            del e.drops[key]
    # Habitat is visited once, never re-stocked on re-entry. Stop expansion at the
    # population/history budget rather than evicting history and farming respawns.
    if tick % 24 == 0 and len(e.habitats) < 256 and len(e.drops) < 128:
        for agent in sorted(world.agents.values(), key=lambda a: a.id):
            if not agent.alive or len(e.habitats) >= 256 or len(e.animals) >= 96:
                continue
            cx, cy = agent.position.x // 8, agent.position.y // 8
            key = f"{cx},{cy}"
            if key in e.habitats:
                continue
            e.habitats.append(key)
            for i in range(2):
                p = Position(
                    x=cx * 8 + int(sample(world.config.seed, cx, cy, f"fauna-x{i}") * 8),
                    y=cy * 8 + int(sample(world.config.seed, cx, cy, f"fauna-y{i}") * 8),
                )
                tile = access.tile(p)
                if tile and tile.walkable and tile.terrain in (Terrain.GRASS, Terrain.SOIL):
                    identifier = f"animal:{key}:{i}"
                    species = ("sheep", "cow", "chicken")[
                        int(sample(world.config.seed, cx, cy, f"species{i}") * 3)
                    ]
                    e.animals[identifier] = Animal(
                        id=identifier, species=species, position=p, born_tick=tick - 240
                    )
                    messages.append(
                        (
                            "ANIMAL_APPEARED",
                            {"message": f"A wild {species} appeared in habitat {key}"},
                        )
                    )
                    if len(e.animals) >= 96:
                        break
    occupied = {(a.position.x, a.position.y) for a in world.agents.values() if a.alive}
    occupied |= {(a.position.x, a.position.y) for a in e.animals.values()}
    for animal in list(e.animals.values()):
        if tick % 24 == 0:
            animal.hunger = min(100, animal.hunger + 1)
            if animal.hunger == 100:
                animal.health = max(0, animal.health - 2)
        # Grazing depletes a real nearby fiber resource; no free feeding or regrowth.
        if animal.hunger >= 30 and tick % 24 == 0:
            patches = sorted(
                (
                    r
                    for r in access.visible_resources(animal.position, 1)
                    if r.kind == "fiber" and r.quantity > 0
                ),
                key=lambda r: r.id,
            )
            if patches:
                access.harvest(patches[0], 1)
                animal.hunger = max(0, animal.hunger - 20)
        if animal.health == 0:
            drop_inventory(
                world,
                f"carcass:{animal.id}:{tick}",
                animal.position,
                Inventory(food=2),
                tick,
            )
            del e.animals[animal.id]
            messages.append(("ANIMAL_DIED", {"message": f"A {animal.species} died"}))
            continue
        if tick % 12:
            continue
        choices = []
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            p = Position(x=animal.position.x + dx, y=animal.position.y + dy)
            tile = access.tile(p)
            if tile and tile.walkable and ((p.x, p.y) not in occupied or p == animal.position):
                choices.append(p)
        if choices:
            nearby = [
                a.position
                for a in world.agents.values()
                if a.alive and a.position.distance(animal.position) <= 5
            ]

            def preference(p, nearby=nearby, animal=animal):
                flee = min((p.distance(v) for v in nearby), default=0)
                owner = world.agents.get(animal.owner_id or "")
                return (
                    flee if animal.frightened_until > tick else 0,
                    -p.distance(owner.position)
                    if owner and owner.alive and p.distance(owner.position) <= 8
                    else 0,
                    sample(world.config.seed, p.x, p.y, f"{animal.id}:{tick}"),
                )

            occupied.discard((animal.position.x, animal.position.y))
            animal.position = max(choices, key=preference)
            occupied.add((animal.position.x, animal.position.y))
    if tick % 8 == 0:
        for crop in e.crops.values():
            if not crop.health or crop.growth == 80:
                continue
            if weather["weather"] in ("rain", "storm"):
                crop.moisture = min(100, crop.moisture + 8)
            elif wet_near(access, crop.position):
                crop.moisture = min(100, crop.moisture + 2)
            else:
                crop.moisture = max(0, crop.moisture - 1)
            if crop.moisture > 0 and not weather["night"]:
                crop.growth = min(80, crop.growth + 1)
                if crop.growth == 80:
                    messages.append(
                        (
                            "CROP_RIPENED",
                            {"message": f"A crop planted by {crop.owner_id} is ready to harvest"},
                        )
                    )
            elif crop.moisture == 0:
                crop.health = max(0, crop.health - 2)
    return messages
