"""Local, material-conserving terrain editing for the two-dimensional world."""

from app.simulation.actions.provisions import carrying_room
from app.simulation.engineering.invention import best_tool
from app.simulation.models.domain import Action, Terrain, Tile

EARTHWORK_ACTIONS = (Action.DIG, Action.MINE, Action.PLACE_BLOCK)
EXTRACTION = {Terrain.SOIL: (Action.DIG, "clay"), Terrain.ROCK: (Action.MINE, "stone")}
BLOCKS = {"stone": (Terrain.ROCK, False), "clay": (Terrain.SOIL, True)}


def validate(world, intent, access):
    a, target = world.agents[intent.actor_id], intent.target
    if not world.config.infinite:
        return "Terrain editing requires a modern world"
    if target is None or a.position.distance(target) != 1:
        return "Terrain work requires an adjacent tile"
    if intent.amount != 1:
        return "Terrain work changes one block at a time"
    tile = access.tile(target)
    if tile is None:
        return "Invalid terrain work site"
    if a.energy < 6:
        return "Not enough energy for terrain work"
    if world.ecosystem and any(c.position == target for c in world.ecosystem.crops.values()):
        return "Cannot alter planted terrain"
    if world.ecosystem and any(v.position == target for v in world.ecosystem.animals.values()):
        return "Cannot alter terrain occupied by an animal"
    if any(b.position == target for b in world.buildings.values()):
        return "Cannot alter terrain beneath a structure or ruin"
    if any(b.alive and b.position == target for b in world.agents.values()):
        return "Cannot alter occupied terrain"
    # Natural nodes have their own harvesting/regrowth lifecycle. Editing underneath
    # them must not manufacture a second source or leave berries on a stone block.
    if any(r.position == target for r in access.visible_resources(target, 0)):
        return "Harvest nodes cannot be replaced by terrain work"
    if intent.action == Action.PLACE_BLOCK:
        if intent.item not in BLOCKS:
            return "Only stone and earth blocks are supported"
        if tile.terrain not in (Terrain.PATH, Terrain.GRASS, Terrain.SAND):
            return "Blocks require clear land; use a bridge to cross water"
        if getattr(a.inventory, intent.item) < 1:
            return "No carried block material"
        return None
    recipe = EXTRACTION.get(tile.terrain)
    if recipe is None or recipe[0] != intent.action:
        return "This terrain cannot be extracted with that action"
    if carrying_room(a.inventory, recipe[1]) < 1:
        return "No carrying room for extracted material"
    if intent.action == Action.MINE and best_tool(a, "mine")[1] < 0.3:
        return "Rock requires a tool with tested mining performance"
    return None


def resolve(world, intent, access):
    a, target = world.agents[intent.actor_id], intent.target
    if intent.action == Action.PLACE_BLOCK:
        terrain, walkable = BLOCKS[intent.item]
        setattr(a.inventory, intent.item, getattr(a.inventory, intent.item) - 1)
        verb = f"placed a {intent.item} block"
    else:
        item = EXTRACTION[access.tile(target).terrain][1]
        setattr(a.inventory, item, getattr(a.inventory, item) + 1)
        terrain, walkable = Terrain.PATH, True
        if intent.action == Action.MINE:
            tool, _ = best_tool(a, "mine")
            a.inventory.tools[tool] -= 1
        verb = f"extracted {item} and opened a passage"
    world.terrain_modifications[f"{target.x},{target.y}"] = Tile(
        position=target.model_copy(), terrain=terrain, walkable=walkable
    )
    a.energy -= 6
    return f"{a.name} {verb} at ({target.x}, {target.y})"
