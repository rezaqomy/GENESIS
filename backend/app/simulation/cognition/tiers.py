"""Bounded, deterministic memory. Reads never mutate an observation or the world."""

from app.simulation.models.domain import (
    Action,
    AgentMemory,
    MemoryRecord,
    PracticalLesson,
    ResourceFact,
)

SHORT_TTL = 48
FACT_TTL = 240


def context_for(agent, environment):
    return ("night" if environment.get("night") else "day") + (
        ":exposed" if agent.psychology.sense_of_safety < 0.4 else ":safe"
    )


def ensure_memory(agent):
    if agent.memory is None:
        agent.memory = AgentMemory()
    return agent.memory


def retain(agent, record):
    memory = ensure_memory(agent)
    recent = [m for m in memory.short_term if 0 <= record.tick - m.tick <= SHORT_TTL]
    memory.short_term = [m for m in recent if m.id != record.id][-23:] + [record]
    # Routine movement/rest does not crowd important experiences out of long-term memory.
    if record.importance >= 0.65:
        archive = {m.id: m for m in memory.long_term}
        archive[record.id] = record
        memory.long_term = sorted(
            archive.values(),
            key=lambda m: (m.importance / (1 + max(0, record.tick - m.tick) / 960), m.tick, m.id),
            reverse=True,
        )[:64]


def observe_food(agent, resources, tick):
    memory = ensure_memory(agent)
    facts = {
        key: fact
        for key, fact in memory.facts.items()
        if 0 <= tick - fact.observed_tick <= FACT_TTL
    }
    for resource in resources:
        if resource.kind == "food":
            facts[resource.id] = ResourceFact(
                resource_id=resource.id,
                position=resource.position.model_copy(),
                quantity=resource.quantity,
                observed_tick=tick,
            )
    # Keep nearby/recent observations, including explicit observations of depletion.
    memory.facts = dict(
        sorted(
            facts.items(),
            key=lambda item: (
                -item[1].observed_tick,
                agent.position.distance(item[1].position),
                item[0],
            ),
        )[:64]
    )
    memory.short_term = [m for m in memory.short_term if 0 <= tick - m.tick <= SHORT_TTL]


def food_destinations(agent, tick):
    if agent.memory is None:
        # Old saves retain their original food observations until the writer upgrades them.
        from app.simulation.models.domain import Position

        return [
            Position(x=int(key.split(":")[1]), y=int(key.split(":")[2]))
            for key, quantity in agent.food_memory.items()
            if quantity > 0
        ]
    facts = [
        fact
        for fact in agent.memory.facts.values()
        if fact.quantity > 0 and 0 <= tick - fact.observed_tick <= FACT_TTL
    ]
    return [
        f.position
        for f in sorted(
            facts,
            key=lambda f: (
                agent.position.distance(f.position) + (tick - f.observed_tick) / 12,
                f.resource_id,
            ),
        )
    ]


def retrieve(agent, tick, environment, goal="", limit=6):
    """Structured relevance + importance + recency; deduplicate across tiers."""
    if agent.memory is None:
        return []
    memory = agent.memory
    records = {m.id: m for m in memory.long_term if m.tick <= tick}
    records.update({m.id: m for m in memory.short_term if 0 <= tick - m.tick <= SHORT_TTL})
    context = context_for(agent, environment)

    def rank(m):
        relevance = (
            (1.0 if goal and m.goal == goal else 0)
            + (0.4 if m.context == context else 0)
            + 0.4 / (1 + agent.position.distance(m.position) / 8)
            + (0.3 if m.peer_id in agent.nearby_agents else 0)
        )
        recency = 1 / (1 + (tick - m.tick) / 48)
        return (relevance + 0.6 * m.importance + 0.4 * recency, m.tick, m.id)

    return sorted(records.values(), key=rank, reverse=True)[: min(6, max(0, limit))]


def goal_adjustment(agent, goal, tick, environment):
    if agent.memory is None:
        return agent.habits.get(goal, 0) * 0.08
    context = context_for(agent, environment)
    lessons = [
        lesson
        for lesson in agent.memory.lessons.values()
        if lesson.goal == goal and lesson.context == context and lesson.updated_tick <= tick
    ]
    if not lessons:
        return 0.0
    weights = [
        min(1, lesson.samples / 5) / (1 + (tick - lesson.updated_tick) / 240) for lesson in lessons
    ]
    return round(
        0.12
        * sum(v.mean_outcome * w for v, w in zip(lessons, weights, strict=True))
        / max(1, sum(weights)),
        4,
    )


def avoided_tiles(agent, tick):
    """Temporary local movement failures must not become permanent global goal aversion."""
    if agent.memory is None:
        return set()
    counts = {}
    for m in agent.memory.short_term:
        if (
            m.kind == "failure"
            and m.action == Action.MOVE
            and m.target is not None
            and 0 <= tick - m.tick <= 6
            and m.text in ("Target tile is blocked", "Target tile is occupied")
        ):
            key = (m.target.x, m.target.y)
            counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count >= 2}


def action_snapshot(actor):
    if actor is None:
        return None
    return {
        "hunger": actor.hunger,
        "food": actor.inventory.food,
        "products": dict(actor.inventory.products),
        "materials": actor.inventory.model_dump(),
        "energy": actor.energy,
        "assembly_trials": len(actor.workshop.trials) if actor.workshop else 0,
        "housing_trials": len(actor.housing.trials) if actor.housing else 0,
        "loneliness": actor.psychology.loneliness,
        "inventory": actor.inventory.total,
        "position": actor.position.model_copy(),
    }


def action_outcome(actor, intent, accepted, before):
    if not accepted:
        return -0.8
    if before is None:
        return 0.0
    # Reward actual effects rather than merely passing action validation.
    if intent.action == Action.EAT:
        return min(1, (before["hunger"] - actor.hunger) / 35)
    if intent.action == Action.REST:
        return min(1, (actor.energy - before["energy"]) / 20) * 0.6
    if intent.action == Action.GATHER:
        return min(1, (actor.inventory.total - before["inventory"]) / 2) * 0.7
    if intent.action == Action.SOCIALIZE:
        return min(1, (before["loneliness"] - actor.psychology.loneliness) / 0.12) * 0.7
    if intent.action == Action.MOVE:
        if intent.destination is None:
            return 0.0
        progress = before["position"].distance(intent.destination) - actor.position.distance(
            intent.destination
        )
        return max(-0.05, min(0.05, progress * 0.05))
    if intent.action == Action.EXPERIMENT_ASSEMBLY:
        if actor.workshop and len(actor.workshop.trials) > before.get("assembly_trials", 0):
            return 0.5 if max(actor.workshop.trials[-1].measured.values()) >= 0.3 else -0.3
        return 0.05
    if intent.action == Action.HEAT:
        improved = any(
            v > before.get("products", {}).get(k, 0) for k, v in actor.inventory.products.items()
        )
        improved |= actor.inventory.fuel > before["materials"]["fuel"]
        return 0.5 if improved else -0.3
    if intent.action == Action.OPERATE:
        return (
            0.5
            if (
                actor.inventory.total > before["inventory"] or actor.inventory.food > before["food"]
            )
            else 0.0
        )
    if intent.action in (Action.ASSEMBLE, Action.ACCEPT_TRADE):
        return 0.5
    if intent.action in (Action.BUILD, Action.CRAFT, Action.REFUEL):
        return 0.5
    if intent.action == Action.EXPERIMENT:
        if actor.housing and len(actor.housing.trials) > before.get("housing_trials", 0):
            return 0.4 if actor.housing.trials[-1].stood else -0.3
        return 0.05
    if intent.action in (Action.STORE, Action.WITHDRAW):
        return 0.25 if actor.inventory.total != before["inventory"] else 0.0
    return 0.0


def learn(agent, record):
    # Navigation progress/failures stay local; they do not teach that an entire goal is bad.
    if record.action in (Action.MOVE, Action.IDLE) or not record.goal:
        return
    memory = ensure_memory(agent)
    key = f"{record.goal}|{record.action}|{record.context}"
    previous = memory.lessons.get(key)
    samples = previous.samples if previous else 0
    # Bounded moving estimate adapts when previously useful behavior stops working.
    rate = 1 / min(10, samples + 1)
    mean = (previous.mean_outcome if previous else 0) * (1 - rate) + record.outcome * rate
    lesson = PracticalLesson(
        goal=record.goal,
        action=record.action,
        context=record.context,
        samples=samples + 1,
        mean_outcome=round(mean, 4),
        updated_tick=record.tick,
    )
    lessons = {k: v for k, v in memory.lessons.items() if k != key}
    memory.lessons = dict(list(lessons.items())[-31:] + [(key, lesson)])
    if lesson.samples >= 3 and (lesson.samples == 3 or lesson.samples % 6 == 0):
        # Grounded statistical consolidation, not an invented model-generated thought.
        retain(
            agent,
            MemoryRecord(
                id=f"lesson:{key}",
                tick=record.tick,
                kind="reflection",
                text=f"{record.action} for {record.goal} in {record.context}: "
                f"mean outcome {lesson.mean_outcome:+.2f} over {lesson.samples} attempts.",
                goal=record.goal,
                action=record.action,
                context=record.context,
                outcome=lesson.mean_outcome,
                importance=0.7,
                position=record.position.model_copy(),
            ),
        )


def memory_context(agent, tick, environment, goal=""):
    records = retrieve(agent, tick, environment, goal)
    memory = agent.memory
    return {
        "recalled": [
            {
                "id": m.id,
                "tick": m.tick,
                "kind": m.kind,
                "text": m.text[:160],
                "goal": m.goal,
                "outcome": m.outcome,
            }
            for m in records
        ],
        "food_facts": [
            {
                **f.model_dump(mode="json"),
                "confidence": round(1 / (1 + (tick - f.observed_tick) / 48), 3),
            }
            for f in sorted(
                memory.facts.values() if memory else [],
                key=lambda f: (
                    agent.position.distance(f.position),
                    -f.observed_tick,
                    f.resource_id,
                ),
            )
            if 0 <= tick - f.observed_tick <= FACT_TTL
        ][:6],
        "lessons": [
            v.model_dump()
            for v in sorted(
                memory.lessons.values() if memory else [],
                key=lambda v: (-v.updated_tick, v.goal, v.action, v.context),
            )
            if v.context == context_for(agent, environment)
        ][:6],
        "legacy_recent": [m.model_dump() for m in agent.memories[-4:]] if memory is None else [],
        "task": {
            "kind": agent.task.kind,
            "stage": agent.task.stage,
            "status": agent.task.status,
            "deadline": agent.task.deadline,
        }
        if agent.task
        else None,
        "verified_skills": [
            s.model_dump()
            for s in sorted(
                agent.skills.values(), key=lambda s: (-s.updated_tick, s.kind, s.context)
            )
        ][:3],
    }
