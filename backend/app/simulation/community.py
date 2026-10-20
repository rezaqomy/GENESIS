"""Local public projects and physically verified help, without global agent awareness."""

from app.simulation.actions.provisions import carrying_room
from app.simulation.cognition.memory import remember
from app.simulation.cognition.tiers import context_for, retain
from app.simulation.engineering.housing import HOUSING, best_design, construction_cost, tested
from app.simulation.models.domain import (
    Action,
    CommunityProject,
    CommunityState,
    Episode,
    MemoryRecord,
)
from app.simulation.settlements.effects import building_usable
from app.simulation.settlements.environment import affinity, conditions

COMMUNITY_ACTIONS = (Action.GIVE, Action.REPAIR, Action.PROPOSE_PROJECT)


def civic(settlement):
    if settlement.community is None:
        settlement.community = CommunityState()
    return settlement.community


def active_project(settlement):
    if settlement.community:
        return next((p for p in settlement.community.projects if p.status == "active"), None)
    return None


def contribute(world, agent, category, amount=1):
    s = world.settlements.get(agent.settlement_id or "")
    if s is None:
        return
    state = civic(s)
    ledger = state.contributions.setdefault(agent.id, {})
    ledger[category] = ledger.get(category, 0) + amount


def validate(world, intent, access):
    a = world.agents[intent.actor_id]
    if intent.action == Action.GIVE:
        peer = world.agents.get(intent.peer_id or "")
        if peer is None or not peer.alive or peer.id == a.id:
            return "A living distinct recipient is required"
        if a.position.distance(peer.position) > 1:
            return "Recipient must be within one tile"
        if intent.item != "food" or a.inventory.food < intent.amount:
            return "Only available carried meals can be given"
        if carrying_room(peer.inventory, "food") < intent.amount:
            return "Recipient has no room for these meals"
    elif intent.action == Action.REPAIR:
        b = world.buildings.get(intent.building_id or "")
        if b is None or not building_usable(b) or b.durability >= 90:
            return "Repair needs a standing, damaged structure"
        if a.position.distance(b.position) > 1 or a.energy < 4:
            return "Repair requires proximity and energy"
        if b.kind in HOUSING and b.design and not tested(a, b.design):
            return "Study the shelter design before maintaining it"
        from app.simulation.actions.construction import affordable, materials

        if not affordable({"wood": 1}, materials(world, a, b.position)):
            return "Repair requires one unit of wood"
    else:
        s = world.settlements.get(a.settlement_id or "")
        if s is None or a.position.distance(s.center) > 2:
            return "Post projects at the community meeting place"
        if active_project(s):
            return "The community already has an active project"
        target = intent.target
        if target is None or target.distance(s.center) > 8:
            return "Project must be within the settlement"
        from app.simulation.observation.builder import build_observation
        from app.simulation.policies.projects import propose_project

        proposal = propose_project(build_observation(world, a.id, access=access))
        if proposal is None or proposal[0] != intent.building_kind or proposal[1] != target:
            return "Project must address an observed local need"
        if intent.building_kind in HOUSING and best_design(a) is None:
            return "A shelter proposal requires a tested design"
    return None


def resolve(world, intent, access):
    a = world.agents[intent.actor_id]
    if intent.action == Action.GIVE:
        peer = world.agents[intent.peer_id]
        a.inventory.food -= intent.amount
        peer.inventory.food += intent.amount
        contribute(world, a, "care", intent.amount)
        s = world.settlements.get(a.settlement_id or "")
        if s:
            civic(s).meals_given += intent.amount
        text = f"{a.name} gave {intent.amount} meal(s) to {peer.name}"
        env = conditions(world.config.seed, world.tick + 1)
        for person, other in ((a, peer), (peer, a)):
            person.relationships[other.id] = affinity(
                person.relationships.get(other.id, 0.5) + 0.08
            )
            remember(
                person,
                Episode(tick=world.tick + 1, kind="help", text=text, peer_id=other.id, outcome=0.8),
            )
            retain(
                person,
                MemoryRecord(
                    id=f"help:{world.tick + 1}:{a.id}:{peer.id}",
                    tick=world.tick + 1,
                    kind="action",
                    text=text,
                    goal="help_neighbor",
                    action=Action.GIVE,
                    peer_id=other.id,
                    context=context_for(person, env),
                    outcome=0.8,
                    importance=0.9,
                    position=person.position.model_copy(),
                ),
            )
        a.current_action = Action.GIVE
        return text
    if intent.action == Action.REPAIR:
        from app.simulation.actions.construction import materials, pay

        b = world.buildings[intent.building_id]
        pay({"wood": 1}, materials(world, a, b.position))
        b.durability = min(100, b.durability + 20)
        a.energy -= 4
        a.current_action = Action.REPAIR
        if a.id not in b.contributors:
            b.contributors = [*b.contributors, a.id][-30:]
        contribute(world, a, "maintenance")
        s = world.settlements.get(a.settlement_id or "")
        if s:
            civic(s).repairs += 1
        return f"{a.name} repaired {b.kind} to {b.durability}% durability"
    s = world.settlements[a.settlement_id]
    state = civic(s)
    p = CommunityProject(
        id=f"project:{s.id}:{world.tick + 1}",
        kind=intent.building_kind,
        target=intent.target.model_copy(),
        proposer_id=a.id,
        created_tick=world.tick + 1,
        deadline=world.tick + 961,
        cost=construction_cost(intent.building_kind, best_design(a)),
        design=best_design(a) if intent.building_kind in HOUSING else None,
    )
    state.projects = [*state.projects, p][-6:]
    a.current_action = Action.PROPOSE_PROJECT
    return f"{a.name} proposed a shared {p.kind} project; materials needed: {p.cost}"


def record_work(world, actor, intent, accepted):
    """Count actual work only, not promises or unverified spoken claims."""
    if not accepted or actor is None or not actor.alive:
        return
    s = world.settlements.get(actor.settlement_id or "")
    if s is None:
        return
    category = None
    if intent.action == Action.STORE:
        category = (
            "food_supply"
            if intent.item == "food"
            else ("farming" if intent.item == "water" else "materials")
        )
    elif intent.action == Action.BUILD:
        category = "construction"
    elif intent.action == Action.REFUEL:
        category = "maintenance"
    if category:
        contribute(world, actor, category, intent.amount if intent.action == Action.STORE else 1)
    p = active_project(s)
    if p and (
        (intent.action == Action.BUILD and intent.target == p.target)
        or (intent.action == Action.STORE and intent.item in p.cost)
    ):
        p.contributors[actor.id] = p.contributors.get(actor.id, 0) + 1


def update_projects(world, tick):
    events = []
    for s in world.settlements.values():
        p = active_project(s)
        if p is None:
            continue
        b = next(
            (b for b in world.buildings.values() if b.position == p.target and b.kind == p.kind),
            None,
        )
        if b and building_usable(b):
            p.status = "completed"
            civic(s).projects_completed += 1
            events.append(
                (
                    "COMMUNITY_PROJECT_COMPLETED",
                    {
                        "message": f"{s.name} completed shared {p.kind}; "
                        f"{len(p.contributors)} actual contributor(s)",
                        "project_id": p.id,
                    },
                )
            )
        elif tick >= p.deadline:
            p.status = "expired"
            events.append(
                (
                    "COMMUNITY_PROJECT_EXPIRED",
                    {
                        "message": f"{s.name} abandoned unfinished {p.kind} project "
                        "after its deadline",
                        "project_id": p.id,
                    },
                )
            )
    return events
