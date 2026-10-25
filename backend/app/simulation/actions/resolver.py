from app.simulation.actions.provisions import carrying_room
from app.simulation.chunks.access import WorldAccess
from app.simulation.models.domain import RESOURCE_KINDS, Action, AgentIntent, WorldState
from app.simulation.settlements.effects import building_usable


def validate_intent(
    world: WorldState, intent: AgentIntent, access: WorldAccess | None = None
) -> str | None:
    access = access or WorldAccess(world)
    agent = world.agents.get(intent.actor_id)
    if agent is None or not agent.alive:
        return "Actor is absent or dead"
    if intent.idea is not None and (intent.utterance is None or intent.action != Action.SOCIALIZE):
        return "Sharing an idea requires a real local conversation"
    if intent.utterance is not None:
        peer = world.agents.get(intent.peer_id or "")
        if (
            intent.action != Action.SOCIALIZE
            or peer is None
            or not peer.alive
            or peer.id == agent.id
            or agent.position.distance(peer.position) > 1
        ):
            return "Dialogue requires a living adjacent listener"
    from app.simulation.actions.ecosystem import ECO_ACTIONS
    from app.simulation.actions.ecosystem import validate as validate_ecosystem

    if intent.action in ECO_ACTIONS:
        return validate_ecosystem(world, intent, access)
    from app.simulation.actions.workshop import WORKSHOP_ACTIONS

    if intent.action in WORKSHOP_ACTIONS:
        from app.simulation.actions.workshop import validate as validate_workshop

        return validate_workshop(world, intent, access)
    from app.simulation.actions.earthwork import EARTHWORK_ACTIONS

    if intent.action in EARTHWORK_ACTIONS:
        from app.simulation.actions.earthwork import validate as validate_earthwork

        return validate_earthwork(world, intent, access)
    from app.simulation.community import COMMUNITY_ACTIONS, validate

    if intent.action in COMMUNITY_ACTIONS:
        return validate(world, intent, access)
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
        room = (
            carrying_room(agent.inventory, resource.kind)
            if world.config.infinite
            else agent.inventory.capacity - agent.inventory.total
        )
        if room <= 0:
            return "Inventory is full or remaining space reserved for food"
        if agent.energy < 3:
            return "Not enough energy"
    elif intent.action == Action.DISCARD:
        if intent.item not in RESOURCE_KINDS or intent.item == "food":
            return "Only non-food materials can be discarded"
        if getattr(agent.inventory, intent.item) < intent.amount:
            return "Not enough material to discard"
    elif intent.action == Action.SOCIALIZE:
        if not any(
            a.alive and a.id != agent.id and a.position.distance(agent.position) <= 1
            for a in world.agents.values()
        ):
            return "No companion within one tile"
    elif (
        intent.action == Action.EAT
        and agent.inventory.food <= 0
        and agent.inventory.products.get("cooked_food", 0) <= 0
    ):
        return "No food in inventory"
    if intent.action in (
        Action.STORE,
        Action.WITHDRAW,
        Action.CRAFT,
        Action.BUILD,
        Action.REFUEL,
        Action.EXPERIMENT,
        Action.EXPERIMENT_TOOL,
    ):
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
    from app.simulation.actions.ecosystem import ECO_ACTIONS
    from app.simulation.actions.ecosystem import resolve as resolve_ecosystem

    if intent.action in ECO_ACTIONS:
        return True, resolve_ecosystem(world, intent, access)
    from app.simulation.actions.workshop import WORKSHOP_ACTIONS

    if intent.action in WORKSHOP_ACTIONS:
        from app.simulation.actions.workshop import resolve as resolve_workshop

        return True, resolve_workshop(world, intent, access)
    from app.simulation.actions.earthwork import EARTHWORK_ACTIONS

    if intent.action in EARTHWORK_ACTIONS:
        from app.simulation.actions.earthwork import resolve as resolve_earthwork

        return True, resolve_earthwork(world, intent, access)
    from app.simulation.community import COMMUNITY_ACTIONS, resolve

    if intent.action in COMMUNITY_ACTIONS:
        return True, resolve(world, intent, access)
    if intent.action in (
        Action.STORE,
        Action.WITHDRAW,
        Action.CRAFT,
        Action.BUILD,
        Action.REFUEL,
        Action.EXPERIMENT,
        Action.EXPERIMENT_TOOL,
    ):
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
                    b.kind == "road" and building_usable(b) and b.position == agent.position
                    for b in world.buildings.values()
                ):
                    cost = 1
            agent.energy = max(0, agent.energy - cost)
            if world.config.infinite and agent.position.distance(agent.home) <= 8:
                agent.exploration_steps = 0
            message = f"{agent.name} moved to ({agent.position.x}, {agent.position.y})"
        case Action.GATHER:
            resource = access.resource(intent.resource_id)
            from app.simulation.engineering.invention import best_tool

            purpose = "cut" if resource.kind == "wood" else "mine"
            tool, effectiveness = (
                best_tool(agent, purpose)
                if resource.kind in ("wood", "stone", "ore", "fuel")
                else (None, 0)
            )
            amount = min(
                resource.quantity,
                (
                    carrying_room(agent.inventory, resource.kind)
                    if world.config.infinite
                    else agent.inventory.capacity - agent.inventory.total
                ),
                2 if effectiveness >= 0.3 else 1,
            )
            access.harvest(resource, amount)
            setattr(
                agent.inventory, resource.kind, getattr(agent.inventory, resource.kind) + amount
            )
            if tool and effectiveness >= 0.3:
                agent.inventory.tools[tool] -= 1
            agent.energy = max(0, agent.energy - 3)
            message = f"{agent.name} gathered {resource.kind}"
        case Action.DISCARD:
            setattr(
                agent.inventory, intent.item, getattr(agent.inventory, intent.item) - intent.amount
            )
            message = (
                f"{agent.name} abandoned {intent.amount} {intent.item} to make room for provisions"
            )
        case Action.EAT:
            cooked = agent.inventory.products.get("cooked_food", 0) > 0
            if cooked:
                from app.simulation.engineering.assemblies import change

                change(agent.inventory, "cooked_food", -1)
            else:
                agent.inventory.food -= 1
            agent.hunger = max(0, agent.hunger - (50 if cooked else 35))
            message = f"{agent.name} ate {'a cooked meal' if cooked else 'berries'}"
        case Action.SOCIALIZE:
            if intent.idea is not None:
                from app.simulation.engineering.assemblies import design_id, knowledge

                # A spoken proposal grants no performance knowledge or fabricated object.
                for person in (agent, world.agents.get(intent.peer_id or "")):
                    if person is not None:
                        k = knowledge(person)
                        ideas = [d for d in k.proposals if design_id(d) != design_id(intent.idea)]
                        k.proposals = [*ideas, intent.idea.model_copy(deep=True)][-4:]
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
        # Modern worlds use days rather than a few dozen decisions as a hunger clock.
        if not world.config.infinite or (world.tick + 1) % 8 == 0:
            agent.hunger = min(100, agent.hunger + 1)
        agent.energy = max(0, agent.energy - 1)
        if world.config.infinite:
            continue  # Resolve health after actions, allowing a last-minute meal.
        if agent.hunger >= 90:
            agent.health = max(0, agent.health - 3)
        elif agent.hunger < 50 and agent.energy > 35:
            agent.health = min(100, agent.health + 1)
        if agent.health == 0:
            agent.alive = False
            agent.current_action = Action.IDLE
            agent.destination = None


def resolve_survival(world: WorldState) -> None:
    """Gradual hunger damage, committed after actors have had their turn to eat."""
    tick = world.tick + 1
    for agent in world.agents.values():
        if not agent.alive:
            continue
        if agent.hunger >= 100 and tick % 8 == 0:
            agent.health = max(0, agent.health - 1)
        elif 90 <= agent.hunger < 100 and tick % 24 == 0:
            agent.health = max(0, agent.health - 1)
        elif agent.hunger < 50 and agent.energy > 35 and tick % 8 == 0:
            agent.health = min(100, agent.health + 1)
        if agent.health == 0:
            agent.alive = False
            agent.current_action = Action.IDLE
            agent.destination = None
