"""Deterministic physical damage; only local witnesses learn from structural outcomes."""

from app.simulation.cognition.tiers import retain
from app.simulation.engineering.housing import HOUSING, knowledge
from app.simulation.models.domain import MemoryRecord
from app.simulation.observation.vision import vision_radius
from app.simulation.settlements.effects import building_usable, local_effects


def resistance(building):
    d = building.design
    if d is None:
        return 0.85  # Existing recordings have no experimental design metadata.
    return min(
        0.98,
        0.12
        + building.quality * 0.72
        + (0.12 if d.bracing else 0)
        + (0.08 if d.frame == "stone" else 0),
    )


def weather_damage(world, tick, environment):
    if tick % 12 or environment["weather"] not in ("storm", "rain", "wind"):
        return []
    events = []
    weather = environment["weather"]
    strength = environment.get("wind_strength", 0.95 if weather == "storm" else 0.35)
    for b in world.buildings.values():
        if b.assembly and building_usable(b):
            from app.simulation.engineering.assemblies import MATERIALS

            d = b.assembly.design
            n = sum(p.count for p in d.parts)
            mass_strength = sum(MATERIALS[p.material]["strength"] * p.count for p in d.parts) / n
            joint = {"loose": 0.15, "fiber": 0.65, "clay": 0.45, "fitted": 0.9}[d.joint]
            device_resistance = 0.15 + mass_strength * 0.55 + joint * 0.25
            wind_damage = max(0, strength - device_resistance) * 35 if weather != "rain" else 0
            water_damage = 2 if any(p.material == "fiber" for p in d.parts) else 0.5
            damage = min(b.durability, round(wind_damage + water_damage))
            if damage:
                b.durability -= damage
                b.last_damage_cause, b.last_damage_tick = weather, tick
                text = (
                    f"{d.name} at ({b.position.x}, {b.position.y}) "
                    f"{'collapsed' if b.durability == 0 else 'was damaged'} in {weather}: "
                    f"{damage} durability lost"
                )
                events.append(
                    (
                        "BUILDING_COLLAPSED" if b.durability == 0 else "BUILDING_DAMAGED",
                        {"building_id": b.id, "damage": damage, "cause": weather, "message": text},
                    )
                )
                for a in world.agents.values():
                    if a.alive and a.position.distance(b.position) <= vision_radius(a):
                        retain(
                            a,
                            MemoryRecord(
                                id=f"device-damage:{b.id}:{tick}",
                                tick=tick,
                                kind="reflection",
                                text=text,
                                outcome=-0.5,
                                importance=0.8,
                                position=a.position.model_copy(),
                                target=b.position.model_copy(),
                            ),
                        )
            continue
        if b.kind not in HOUSING or not building_usable(b) or b.design is None:
            continue
        wind_load = strength if weather in ("wind", "storm") else 0.10
        wind_damage = max(0, (wind_load - resistance(b)) * 50)
        wetness = 0.20 if weather == "rain" else 0.25 if weather == "storm" else 0
        rain_damage = wetness * (1 - b.quality) * (2 if b.design.raised_foundation else 12)
        damage = round(wind_damage + rain_damage)
        if damage <= 0:
            continue
        damage = min(b.durability, damage)
        b.durability -= damage
        cause = "wind" if wind_damage >= rain_damage else "rain"
        b.last_damage_cause = cause
        b.last_damage_tick = tick
        collapsed = b.durability == 0
        text = (
            f"{b.kind.replace('_', ' ')} at ({b.position.x}, {b.position.y}) "
            f"{'collapsed' if collapsed else 'was damaged'} in {weather}: "
            f"{damage} durability lost, workmanship {b.quality:.0%}"
        )
        events.append(
            (
                "BUILDING_COLLAPSED" if collapsed else "BUILDING_DAMAGED",
                {"building_id": b.id, "damage": damage, "cause": cause, "message": text},
            )
        )
        for a in world.agents.values():
            if not a.alive:
                continue
            sight = vision_radius(a, local_effects(world, a.position))
            if a.position.distance(b.position) > sight:
                continue
            learn_damage(a, b, tick, text, cause, collapsed)
    return events


def learn_damage(a, b, tick, text, cause, collapsed):
    k = knowledge(a)
    insight = (
        "bracing"
        if cause == "wind" and not b.design.bracing
        else "foundation"
        if not b.design.raised_foundation
        else "roof"
        if b.design.roof == "fiber"
        else "practice"
    )
    if insight not in k.insights:
        k.insights = [*k.insights, insight][-4:]
    if collapsed:
        k.observed_failures = dict(list(k.observed_failures.items())[-31:] + [(b.id, tick)])
        # A promising prototype is revised after a real failed load test.
        for trial in k.trials:
            if trial.design == b.design:
                trial.score = round(trial.score * 0.65, 4)
    retain(
        a,
        MemoryRecord(
            id=f"weather:{tick}:{b.id}",
            tick=tick,
            kind="reflection",
            text=text + f"; next experiment: investigate {insight}",
            goal="experiment_shelter",
            outcome=-1 if collapsed else -0.4,
            importance=0.95,
            position=b.position.model_copy(),
        ),
    )


def observe_ruins(world, actor, tick, sight):
    for b in world.buildings.values():
        if b.kind not in HOUSING or b.design is None or b.durability != 0:
            continue
        if not b.last_damage_cause or actor.position.distance(b.position) > sight:
            continue
        seen_tick = actor.housing.observed_failures.get(b.id, -1) if actor.housing else -1
        if seen_tick >= b.last_damage_tick:
            continue
        text = (
            f"{actor.name} observed collapsed {b.kind} at ({b.position.x}, {b.position.y}); "
            f"visible damage from {b.last_damage_cause}"
        )
        learn_damage(actor, b, tick, text, b.last_damage_cause, True)
