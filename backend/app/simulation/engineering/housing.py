"""Bounded shelter design search; hypotheses become usable only through physical trials."""

from app.simulation.chunks.generator import sample
from app.simulation.cognition.tiers import retain
from app.simulation.models.domain import DesignTrial, HousingKnowledge, MemoryRecord, ShelterDesign

HOUSING = {"shelter", "remote_camp"}


def design_key(design):
    return f"{design.frame}:{design.roof}:{int(design.bracing)}:{int(design.raised_foundation)}"


def knowledge(agent):
    if agent.housing is None:
        agent.housing = HousingKnowledge()
    return agent.housing


def tested(agent, design):
    return bool(agent.housing and any(t.stood and t.design == design for t in agent.housing.trials))


def best_design(agent):
    k = agent.housing
    if not k:
        return None
    choices = [t for t in k.trials if t.stood]
    if not choices:
        return None
    return max(choices, key=lambda t: (t.score, t.tick, design_key(t.design))).design.model_copy()


def propose_design(agent, seed, tick):
    k = agent.housing
    if k and k.experiment:
        return k.experiment.model_copy()
    tried = {design_key(t.design) for t in k.trials} if k else set()
    candidates = [
        ShelterDesign(frame=f, roof=r, bracing=b, raised_foundation=g)
        for f in ("wood", "stone")
        for r in ("fiber", "wood")
        for b in (False, True)
        for g in (False, True)
    ]
    insights = set(k.insights if k else [])
    # Collapse evidence changes the next hypothesis, not the laws of the environment.
    preferred = [
        d
        for d in candidates
        if design_key(d) not in tried
        and ("bracing" not in insights or d.bracing)
        and ("foundation" not in insights or d.raised_foundation)
        and ("roof" not in insights or d.roof == "wood")
    ]
    choices = preferred or [d for d in candidates if design_key(d) not in tried] or candidates
    index = int(
        sample(seed, int(agent.id.split("-")[-1]), tick, "housing-hypothesis") * len(choices)
    )
    return choices[min(index, len(choices) - 1)].model_copy()


def prototype_cost(design):
    cost = {design.frame: 1, "fiber": 1}
    cost[design.roof] = max(cost.get(design.roof, 0), 1)
    if design.bracing:
        cost["wood"] = max(cost.get("wood", 0), 1)
    if design.raised_foundation:
        cost["stone"] = max(cost.get("stone", 0), 1)
    return cost


def construction_cost(kind, design):
    from app.simulation.settlements.effects import BUILD_COSTS

    if kind not in HOUSING or design is None:
        return dict(BUILD_COSTS[kind])
    cost = {"wood": 6 if kind == "shelter" else 3, "fiber": 3 if kind == "shelter" else 2}
    if design.frame == "stone":
        cost["stone"] = cost.pop("wood")
    if design.roof == "wood":
        cost["wood"] = cost.get("wood", 0) + 2
        cost["fiber"] -= 1
    if design.bracing:
        cost["wood"] = cost.get("wood", 0) + 2
        cost["fiber"] += 1
    if design.raised_foundation:
        cost["stone"] = cost.get("stone", 0) + 2
    return cost


def design_strength(design):
    # Physical affordances, not an answer supplied to the decision model.
    return (
        0.30
        + (0.16 if design.frame == "stone" else 0)
        + (0.12 if design.roof == "wood" else 0)
        + (0.24 if design.bracing else 0)
        + (0.16 if design.raised_foundation else 0)
    )


def workmanship(agent, design, seed, tick, salt):
    practice = agent.housing.practice if agent.housing else 0
    skill = min(1, practice / 60)
    variation = (sample(seed, tick, int(agent.id.split("-")[-1]), salt) - 0.5) * 0.12
    return round(
        max(
            0.05,
            min(
                1,
                design_strength(design) * (0.5 + skill * 0.5) * (0.75 + agent.energy / 400)
                + variation,
            ),
        ),
        4,
    )


def experiment(world, actor, intent):
    from app.simulation.actions.construction import materials, pay

    k = knowledge(actor)
    design = intent.design
    source = "study" if intent.building_id else "experiment"
    if k.experiment != design or k.studying_id != intent.building_id:
        k.experiment, k.experiment_steps, k.studying_id = design.model_copy(), 0, intent.building_id
    if k.experiment_steps == 0 and source == "experiment":
        pay(prototype_cost(design), materials(world, actor, actor.position))
    actor.energy = max(0, actor.energy - 3)
    k.practice += 1
    k.experiment_steps += 1
    if k.experiment_steps < 3:
        return f"{actor.name} tested shelter joints and supports ({k.experiment_steps}/3)"
    score = workmanship(actor, design, world.config.seed, world.tick + 1, "prototype-test")
    # Observing a structure is a rehearsal, not instant mastery or a quality guarantee.
    stood = score >= 0.20
    trial = DesignTrial(
        design=design.model_copy(), tick=world.tick + 1, score=score, stood=stood, source=source
    )
    k.trials = [*k.trials, trial][-12:]
    k.experiment, k.experiment_steps, k.studying_id = None, 0, None
    text = (
        f"{actor.name} shelter prototype {'stood' if stood else 'failed'}: "
        f"{design_key(design)}, measured load score {score:.2f}; not storm-tested"
    )
    retain(
        actor,
        MemoryRecord(
            id=f"prototype:{actor.id}:{world.tick + 1}",
            tick=world.tick + 1,
            kind="reflection",
            text=text,
            goal="experiment_shelter",
            outcome=0.4 if stood else -0.4,
            importance=0.85,
            position=actor.position.model_copy(),
        ),
    )
    return text
