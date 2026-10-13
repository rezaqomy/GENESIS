from app.simulation.chunks.access import WorldAccess
from app.simulation.models.domain import Action, AgentIntent, WorldState


def validate_intent(
    world: WorldState, intent: AgentIntent, access: WorldAccess | None = None
) -> str | None:
    access = access or WorldAccess(world)
    agent = world.agents.get(intent.actor_id)
    if agent is None or not agent.alive:
        return "Actor is absent or dead"
    if intent.action == Action.MOVE:
        target = intent.target
        if target is None or agent.position.distance(target) != 1:
            return "Movement must be one adjacent tile"
        tile = access.tile(target)
        if tile is None:
            return "Target is outside the world"
        if not tile.walkable:
            return "Target tile is blocked"
        if agent.energy < 2:
            return "Not enough energy"
        if any(
            a.alive and a.id != agent.id and a.position == target for a in world.agents.values()
        ):
            return "Target tile is occupied"
    elif intent.action == Action.GATHER:
        resource = access.resource(intent.resource_id or "")
        if resource is None or agent.position.distance(resource.position) > 1:
            return "Resource must be within one tile"
        if resource.quantity <= 0:
            return "Resource is depleted"
        if agent.inventory.total >= agent.inventory.capacity:
            return "Inventory is full"
        if agent.energy < 3:
            return "Not enough energy"
    elif intent.action == Action.SOCIALIZE:
        if not any(
            a.alive and a.id != agent.id and a.position.distance(agent.position) <= 1
            for a in world.agents.values()
        ):
            return "No companion within one tile"
    elif intent.action == Action.EAT and agent.inventory.food <= 0:
        return "No food in inventory"
    if intent.action in (Action.STORE, Action.WITHDRAW, Action.CRAFT, Action.BUILD, Action.REFUEL):
        from app.simulation.actions.construction import validate_construction

        return validate_construction(world, intent, access)
    return None


def resolve_intent(
    world: WorldState, intent: AgentIntent, access: WorldAccess | None = None
) -> tuple[bool, str]:
    access = access or WorldAccess(world)
    reason = validate_intent(world, intent, access)
    if reason:
        return False, reason
    agent = world.agents[intent.actor_id]
    agent.current_action = intent.action
    agent.destination = intent.destination
    if intent.action in (Action.STORE, Action.WITHDRAW, Action.CRAFT, Action.BUILD, Action.REFUEL):
        from app.simulation.actions.construction import resolve_construction

        return True, resolve_construction(world, intent, access)
    match intent.action:
        case Action.MOVE:
            if world.config.infinite:
                agent.recent_positions.append(agent.position.model_copy())
                agent.recent_positions = agent.recent_positions[-12:]
            agent.position = intent.target.model_copy()  # validated above
            cost = 2
            if world.config.infinite:
                if any(
                    b.kind == "road" and b.progress == 100 and b.position == agent.position
                    for b in world.buildings.values()
                ):
                    cost = 1
            agent.energy = max(0, agent.energy - cost)
            if world.config.infinite and agent.position.distance(agent.home) <= 8:
                agent.exploration_steps = 0
            message = f"{agent.name} moved to ({agent.position.x}, {agent.position.y})"
        case Action.GATHER:
            resource = access.resource(intent.resource_id)
            tool = (
                "axe"
                if resource.kind == "wood"
                else "pickaxe"
                if resource.kind in ("stone", "ore", "fuel")
                else None
            )
            amount = min(
                resource.quantity,
                agent.inventory.capacity - agent.inventory.total,
                2 if tool and agent.inventory.tools.get(tool, 0) > 0 else 1,
            )
            access.harvest(resource, amount)
            setattr(
                agent.inventory, resource.kind, getattr(agent.inventory, resource.kind) + amount
            )
            if tool and agent.inventory.tools.get(tool, 0) > 0:
                agent.inventory.tools[tool] -= 1
            agent.energy = max(0, agent.energy - 3)
            message = f"{agent.name} gathered {resource.kind}"
        case Action.EAT:
            agent.inventory.food -= 1
            agent.hunger = max(0, agent.hunger - 35)
            message = f"{agent.name} ate berries"
        case Action.SOCIALIZE:
            agent.psychology.loneliness = max(0, agent.psychology.loneliness - 0.12)
            agent.psychology.social_satisfaction = min(
                1, agent.psychology.social_satisfaction + 0.12
            )
            message = f"{agent.name} socialized with a companion"
        case Action.REST:
            recovery = 14
            if world.config.infinite:
                from app.simulation.settlements.effects import local_effects

                effects = local_effects(world, agent.position)
                recovery += int(effects["comfort"] * 10) + min(3, len(agent.nearby_agents))
            agent.energy = min(100, agent.energy + recovery)
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
