"""Typed task recipes inspired by hierarchical planning and verified skill libraries."""

from app.simulation.cognition.tiers import context_for, retain
from app.simulation.models.domain import (
    Action,
    MemoryRecord,
    TaskOutcome,
    TaskPlan,
    VerifiedSkill,
)

RECIPES = {
    "forage": ["acquire", "eat"],
    "construction": ["materials", "build"],
    "expedition": ["provision", "recover", "explore", "return"],
}
START_GOALS = {
    "find_food": "forage",
    "take_shared_food": "forage",
    "eat": "forage",
    "build_shelter": "construction",
    "improve_settlement": "construction",
    "explore": "expedition",
}


def skill_bonus(agent, goal, tick, environment):
    kind = START_GOALS.get(goal)
    skill = agent.skills.get(f"{kind}:{context_for(agent, environment)}")
    if not skill or not skill.successes or tick < skill.updated_tick:
        return 0.0
    confidence = skill.successes / (skill.successes + skill.failures + 2)
    return round(0.04 * confidence / (1 + (tick - skill.updated_tick) / 480), 4)


def select_task(o, chosen, valid, plans):
    """Pure planning: the writer will adopt and update the proposed task after resolution."""
    a = o.self_agent
    task = a.task.model_copy(deep=True) if a.task and a.task.status == "active" else None
    if task is None:
        # A short recovery window prevents endlessly restarting an impossible recipe.
        recent = a.task_history[-1] if a.task_history else None
        kind = START_GOALS.get(chosen)
        if kind is None or (recent and o.tick - recent.ended_tick < 12):
            return None, None
        if kind == "forage" and a.inventory.food >= 2 and a.hunger < 55:
            return None, None
        if chosen == "eat" and a.hunger < 55:
            return None, None
        kwargs = plans[chosen][1]
        task = TaskPlan(
            id=f"{a.id}:{o.tick}:{kind}",
            kind=kind,
            context=context_for(a, o.environment),
            stage=RECIPES[kind][0],
            started_tick=o.tick,
            last_progress_tick=o.tick,
            deadline=o.tick + (240 if kind == "expedition" else 120),
            origin=a.position.model_copy(),
            target=kwargs.get("destination"),
            building_kind=kwargs.get("building_kind"),
            initial_food=a.inventory.food,
            initial_hunger=a.hunger,
        )
    if o.tick >= task.deadline or o.tick - task.last_progress_tick >= 24:
        # Writer records the failure; fallback actions remain available this tick.
        return task, None
    if chosen in (
        "make_food_space",
        "supply_farm",
        "experiment_tool",
        "experiment_shelter",
        "craft_tools",
    ):
        return task, None  # Provisions can interrupt a project without changing its recipe.
    available = {c.goal: c for c in valid}

    def best(goals):
        choices = [available[g] for g in goals if g in available]
        return max(choices, key=lambda c: (c.utility, c.goal)).goal if choices else None

    if task.kind == "forage":
        task.stage = "eat" if a.hunger >= 55 and a.inventory.food else "acquire"
        desired = best(["eat"]) if task.stage == "eat" else best(["find_food", "take_shared_food"])
        if task.stage == "acquire" and chosen in ("find_food", "take_shared_food"):
            desired = chosen
        if desired is None and a.inventory.total >= a.inventory.capacity:
            desired = best(["store_resources"])
    elif task.kind == "construction":
        goals = [
            g
            for g in ("build_shelter", "improve_settlement")
            if g in available
            and plans[g][1].get("destination") == task.target
            and plans[g][1].get("building_kind") == task.building_kind
        ]
        task.stage = (
            "build" if goals else "experiment" if "experiment_shelter" in available else "materials"
        )
        desired = best(
            goals
            or (
                ["experiment_shelter"]
                if "experiment_shelter" in available
                else ["take_materials", "gather_resources", "store_resources"]
            )
        )
    else:
        # Once return starts, improved supplies cannot accidentally restart outbound travel.
        if (
            task.stage == "return"
            or task.exploration_moves >= 16 + int(a.personality.independence * 16)
            or (
                task.max_home_distance > 8
                and (a.energy < 35 or (a.inventory.food == 0 and a.hunger > 55))
            )
        ):
            task.stage = "return"
            desired = best(["return_home", "seek_safety"])
        elif task.stage == "explore":
            desired = best(["explore"])
        elif a.inventory.food < 2:
            task.stage = "provision"
            desired = best(["find_food", "take_shared_food", "store_resources"])
        elif a.energy < 65:
            task.stage = "recover"
            desired = best(["rest"])
        else:
            task.stage = "explore"
            task.target = (
                None  # The first freshly planned exploration action fixes the destination.
            )
            desired = best(["explore"])
    if desired:
        destination = plans[desired][1].get("destination")
        if task.kind != "construction" and destination != task.target:
            task.best_distance = None
            task.target = destination.model_copy() if destination else None
    return task, desired


def finish_task(agent, status, reason, tick):
    task = agent.task
    if not task or task.status != "active":
        return None
    task.status, task.reason = status, reason
    outcome = TaskOutcome(
        id=task.id,
        kind=task.kind,
        status=status,
        reason=reason,
        started_tick=task.started_tick,
        ended_tick=tick,
        actions=task.actions,
        energy_spent=task.energy_spent,
        food_delta=agent.inventory.food - task.initial_food,
        hunger_delta=agent.hunger - task.initial_hunger,
        discoveries=task.discoveries,
    )
    agent.task_history = [*agent.task_history, outcome][-8:]
    key = f"{task.kind}:{task.context}"
    previous = agent.skills.get(key)
    # Failed first attempts do not become verified skills. Peer completion earns no skill.
    if status != "cancelled" and (status == "succeeded" or previous):
        skill = (
            previous.model_copy(deep=True)
            if previous
            else VerifiedSkill(
                kind=task.kind,
                context=task.context,
                stages=RECIPES[task.kind],
                updated_tick=tick,
            )
        )
        if status == "succeeded":
            duration = max(1, tick - task.started_tick)
            skill.mean_ticks = round(
                (skill.mean_ticks * skill.successes + duration) / (skill.successes + 1), 2
            )
            skill.successes += 1
        else:
            skill.failures += 1
        skill.updated_tick = tick
        skills = {k: v for k, v in agent.skills.items() if k != key}
        agent.skills = dict(list(skills.items())[-7:] + [(key, skill)])
    retain(
        agent,
        MemoryRecord(
            id=f"task:{task.id}",
            tick=tick,
            kind="reflection",
            text=f"{task.kind} {status}: {reason}; {outcome.actions} actions, "
            f"{outcome.energy_spent} action energy, food change {outcome.food_delta:+d}.",
            goal=task.kind,
            context=task.context,
            outcome=1 if status == "succeeded" else -0.6 if status == "failed" else 0,
            importance=0.85,
            position=agent.position.model_copy(),
        ),
    )
    return outcome


def update_task(world, actor, intent, accepted, before, tick):
    """Verify physical outcomes, including a whole journey's costs and lack of progress."""
    if actor is None or actor.task is None or actor.task.status != "active":
        return None
    task = actor.task
    if not actor.alive:
        return finish_task(actor, "failed", "Actor died before completing the task", tick)
    if accepted:
        task.actions += 1
        if before:
            task.energy_spent += max(0, before["energy"] - actor.energy)
        task.max_home_distance = max(task.max_home_distance, actor.position.distance(actor.home))
        if intent.action == Action.MOVE:
            from app.simulation.chunks.generator import chunk_coord, chunk_key

            task.moves += 1
            if (
                task.stage == "explore"
                and intent.decision
                and intent.decision.selected_goal == "explore"
            ):
                task.exploration_moves += 1
            if chunk_key(*chunk_coord(actor.position)) not in actor.known_chunks:
                task.discoveries += 1
            destination = task.target
            if destination:
                distance = actor.position.distance(destination)
                if task.best_distance is None or distance < task.best_distance:
                    task.best_distance = distance
                    task.last_progress_tick = tick
        elif (
            task.kind == "forage"
            and before
            and (actor.inventory.food > before["food"] or actor.hunger < before["hunger"])
        ):
            task.last_progress_tick = tick
        elif (
            task.kind == "expedition"
            and before
            and (
                (task.stage == "provision" and actor.inventory.food > before["food"])
                or (task.stage == "recover" and actor.energy > before["energy"])
            )
        ):
            task.last_progress_tick = tick
        elif task.kind == "construction" and before:
            from app.simulation.engineering.housing import best_design, construction_cost

            if any(
                getattr(actor.inventory, material) > before["materials"][material]
                for material in (
                    construction_cost(task.building_kind, best_design(actor))
                    if task.building_kind
                    else {}
                )
            ):
                task.last_progress_tick = tick
        if intent.action == Action.BUILD and intent.target == task.target:
            task.work_units += 1
            task.last_progress_tick = tick
    if task.kind == "forage" and actor.inventory.food >= 2 and actor.hunger < 65:
        return finish_task(
            actor, "succeeded", "Food reserve replenished without urgent hunger", tick
        )
    if task.kind == "construction":
        from app.simulation.observation.vision import vision_radius
        from app.simulation.settlements.effects import building_usable, local_effects

        sight = vision_radius(actor, local_effects(world, actor.position))
        building = next(
            (
                b
                for b in world.buildings.values()
                if b.position == task.target and actor.position.distance(b.position) <= sight
            ),
            None,
        )
        if building and building_usable(building):
            if building.kind == task.building_kind and task.work_units:
                return finish_task(actor, "succeeded", "Contributed to a completed structure", tick)
            return finish_task(
                actor, "cancelled", "Site completed or changed by another builder", tick
            )
    if (
        task.kind == "expedition"
        and task.stage == "return"
        and actor.position.distance(actor.home) <= 8
    ):
        if task.max_home_distance > 8 and task.exploration_moves >= 4:
            return finish_task(actor, "succeeded", "Explored beyond home and returned", tick)
        return finish_task(actor, "failed", "Expedition did not reach beyond home", tick)
    if tick >= task.deadline or tick - task.last_progress_tick >= 24:
        return finish_task(actor, "failed", "Task deadline or no-progress limit reached", tick)
    return None
