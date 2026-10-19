from collections import defaultdict

from app.simulation.chunks.generator import chunk_coord, chunk_key, sample
from app.simulation.models.domain import WorldState


def conditions(seed: int, tick: int) -> dict:
    phase = (tick % 240) / 240
    night = phase >= 0.72 or phase < 0.12
    weather_sample = sample(seed, tick // 120, 0, "weather")
    weather = (
        "storm"
        if weather_sample < 0.08
        else "rain"
        if weather_sample < 0.28
        else "wind"
        if weather_sample < 0.5
        else "clear"
    )
    return {
        "day": tick // 240 + 1,
        "phase": round(phase, 4),
        "night": night,
        "weather": weather,
        "wind_strength": round(
            0.8 + weather_sample if weather == "storm" else 0.35 if weather == "wind" else 0.1, 3
        ),
        "cold": round((0.55 if night else 0.12) + (0.25 if weather in ("rain", "storm") else 0), 3),
    }


class SpatialIndex:
    def __init__(self, world: WorldState, cell_size: int = 8):
        self.size = cell_size
        self.buckets = defaultdict(list)
        for a in world.agents.values():
            if a.alive:
                self.buckets[a.position.x // cell_size, a.position.y // cell_size].append(a)

    def nearby(self, position, radius):
        result = []
        for y in range((position.y - radius) // self.size, (position.y + radius) // self.size + 1):
            for x in range(
                (position.x - radius) // self.size, (position.x + radius) // self.size + 1
            ):
                result.extend(
                    a for a in self.buckets[x, y] if a.position.distance(position) <= radius
                )
        return sorted(result, key=lambda a: a.id)


def clamp(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 4)


def experience_tick(world: WorldState, access) -> None:
    env = conditions(world.config.seed, world.tick + 1)
    index = SpatialIndex(world)
    for a in world.agents.values():
        if not a.alive:
            continue
        from app.simulation.observation.vision import vision_radius
        from app.simulation.settlements.effects import local_effects

        effects = local_effects(world, a.position, index)
        sight = vision_radius(a, effects)
        peers = [b for b in index.nearby(a.position, min(5, sight)) if b.id != a.id]
        a.nearby_agents = [b.id for b in peers]
        compatibility = sum(
            1 - abs(a.personality.sociability - b.personality.sociability) for b in peers
        )
        social = min(1.0, compatibility / 3)
        p, traits = a.psychology, a.personality
        p.loneliness = clamp(p.loneliness + 0.005 * (0.2 + traits.sociability) - social * 0.025)
        p.social_satisfaction = clamp(p.social_satisfaction * 0.94 + social * 0.06)
        for b in peers:
            previous = a.relationships.get(b.id, 0.5)
            a.relationships[b.id] = clamp(
                previous + 0.003 * (1 - abs(traits.sociability - b.personality.sociability))
            )
        safety = clamp(0.45 + min(0.25, len(peers) * 0.05) - env["cold"] * 0.32)
        # Later settlement structures provide local effects through this one boundary.
        if world.settlements:
            safety = effects["safety"]
        else:
            effects = {"comfort": 0.0, "warmth": 0.0}
        if env["night"] and (world.tick + 1) % 12 == 0:
            from app.simulation.engineering.invention import best_tool

            light, effectiveness = best_tool(a, "light")
            if light and effectiveness >= 0.3:
                a.inventory.tools[light] -= 1
        p.sense_of_safety = safety
        p.fear = clamp(p.fear * 0.88 + (1 - safety) * (1 - traits.risk_tolerance) * 0.12)
        distance = a.position.distance(a.home)
        a.time_away = a.time_away + 1 if distance > 10 else 0
        if distance > 10:
            p.homesickness = clamp(p.homesickness + 0.001 * (traits.loyalty + traits.sociability))
        else:
            p.homesickness = clamp(p.homesickness - 0.02)
            p.attachment = clamp(p.attachment + 0.001 * social * traits.loyalty)
        crowding = max(0, len(peers) - 4) / 6
        p.stress = clamp(
            p.stress * 0.94 + (0.3 * p.fear + 0.4 * p.loneliness + 0.3 * crowding) * 0.06
        )
        p.mood = clamp(
            0.4 * (1 - a.hunger / 100)
            + 0.2 * (a.energy / 100)
            + 0.25 * (1 - p.stress)
            + 0.15 * social
        )
        p.satisfaction = clamp(
            p.satisfaction * 0.96 + (0.5 * p.mood + 0.3 * social + 0.2 * effects["comfort"]) * 0.04
        )
        if env["cold"] > 0.5 and effects["warmth"] < 0.3 and effects["comfort"] < 0.3:
            # Manageable exposure, not combat. A warm camp or shelter prevents it.
            if (world.tick + 1) % 8 == 0:
                a.health = max(0, a.health - 1)
        # Knowledge comes only from observed terrain/resources, not camera loads.
        key = chunk_key(*chunk_coord(a.position))
        if key not in a.known_chunks:
            a.known_chunks.append(key)
        a.known_chunks = a.known_chunks[-128:]
        resources = access.visible_resources(a.position, sight)
        from app.simulation.engineering.weathering import observe_ruins

        observe_ruins(world, a, world.tick, sight)
        from app.simulation.cognition.tiers import observe_food

        observe_food(a, resources, world.tick)
        memory = dict(a.food_memory)
        for r in resources:
            if r.kind == "food":
                memory.pop(r.id, None)
                memory[r.id] = r.quantity
            if r.quantity and r.position not in a.discoveries:
                a.discoveries.append(r.position.model_copy())
        a.food_memory = dict(list(memory.items())[-16:])
        a.discoveries = a.discoveries[-48:]
        if a.health == 0:
            a.alive = False
