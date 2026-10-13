from app.simulation.models.domain import Action, AgentIntent, WorldState


def validate_intent(world: WorldState, intent: AgentIntent) -> str | None:
    agent = world.agents.get(intent.actor_id)
    if agent is None or not agent.alive:
        return "Actor is absent or dead"
    if intent.action == Action.MOVE:
        target = intent.target
        if target is None or agent.position.distance(target) != 1:
            return "Movement must be one adjacent tile"
        if not (0 <= target.x < world.config.width and 0 <= target.y < world.config.height):
            return "Target is outside the world"
        if not world.tiles[target.y * world.config.width + target.x].walkable:
            return "Target tile is blocked"
        if agent.energy < 2:
            return "Not enough energy"
        if any(
            a.alive and a.id != agent.id and a.position == target for a in world.agents.values()
        ):
            return "Target tile is occupied"
    elif intent.action == Action.GATHER:
        resource = world.resources.get(intent.resource_id or "")
        if resource is None or agent.position.distance(resource.position) > 1:
            return "Resource must be within one tile"
        if resource.quantity <= 0:
            return "Resource is depleted"
        if agent.inventory.total >= agent.inventory.capacity:
            return "Inventory is full"
        if agent.energy < 3:
            return "Not enough energy"
    elif intent.action == Action.EAT and agent.inventory.food <= 0:
        return "No food in inventory"
    return None


def resolve_intent(world: WorldState, intent: AgentIntent) -> tuple[bool, str]:
    reason = validate_intent(world, intent)
    if reason:
        return False, reason
    agent = world.agents[intent.actor_id]
    agent.current_action = intent.action
    agent.destination = intent.destination
    match intent.action:
        case Action.MOVE:
            agent.position = intent.target.model_copy()  # validated above
            agent.energy = max(0, agent.energy - 2)
            message = f"{agent.name} moved to ({agent.position.x}, {agent.position.y})"
        case Action.GATHER:
            resource = world.resources[intent.resource_id]
            resource.quantity -= 1
            setattr(agent.inventory, resource.kind, getattr(agent.inventory, resource.kind) + 1)
            agent.energy = max(0, agent.energy - 3)
            message = f"{agent.name} gathered {resource.kind}"
        case Action.EAT:
            agent.inventory.food -= 1
            agent.hunger = max(0, agent.hunger - 35)
            message = f"{agent.name} ate berries"
        case Action.REST:
            agent.energy = min(100, agent.energy + 14)
            message = f"{agent.name} rested"
        case _:
            message = f"{agent.name} waited"
    return True, message


def advance_physiology(world: WorldState) -> None:
    for agent in world.agents.values():
        if not agent.alive:
            continue
        agent.hunger = min(100, agent.hunger + 1)
        agent.energy = max(0, agent.energy - 1)
        if agent.hunger >= 90:
            agent.health = max(0, agent.health - 3)
        elif agent.hunger < 50 and agent.energy > 35:
            agent.health = min(100, agent.health + 1)
        if agent.health == 0:
            agent.alive = False
            agent.current_action = Action.IDLE
            agent.destination = None
