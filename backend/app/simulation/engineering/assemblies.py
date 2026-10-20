"""Compositional stationary inventions. Planning never calls the physical evaluator."""

import hashlib
import json
import random
from collections import Counter

from app.simulation.models.domain import AssemblyDesign, AssemblyPart, WorkshopKnowledge

PRODUCTS = ("metal", "ceramic", "cooked_food")
MATERIALS = {
    "wood": {"strength": 0.5, "insulation": 0.1, "burn": 0.9, "seal": 0.3},
    "stone": {"strength": 0.9, "insulation": 0.8, "burn": 0, "seal": 0.5},
    "fiber": {"strength": 0.25, "insulation": 0.05, "burn": 1, "seal": 0.1},
    "clay": {"strength": 0.35, "insulation": 0.7, "burn": 0, "seal": 0.9},
    "ore": {"strength": 0.7, "insulation": 0.6, "burn": 0, "seal": 0.4},
    "metal": {"strength": 1, "insulation": 0.5, "burn": 0, "seal": 1},
    "ceramic": {"strength": 0.65, "insulation": 1, "burn": 0, "seal": 1},
}
CAPABILITIES = ("catch", "water", "heat", "cultivate", "shelter", "storage")


def knowledge(a):
    if a.workshop is None:
        a.workshop = WorkshopKnowledge()
    return a.workshop


def design_id(d):
    # Labels and the order of identical parts do not create new physical discoveries.
    parts = Counter()
    for p in d.parts:
        parts[p.material, p.shape] += p.count
    data = {
        "parts": sorted((m, s, n) for (m, s), n in parts.items()),
        "joint": d.joint,
        "mechanism": d.mechanism,
        "enclosed": d.enclosed,
    }
    return "assembly:" + hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


def cost(d):
    c = Counter()
    for p in d.parts:
        c[p.material] += p.count
    if d.joint in ("fiber", "clay"):
        c[d.joint] += 1
    return dict(c)


def quantity(inv, item):
    return inv.products.get(item, 0) if item in PRODUCTS else getattr(inv, item, 0)


def change(inv, item, delta):
    if item in PRODUCTS:
        # Assign rather than mutating the default dict, preserving field presence in old logs.
        inv.products = inv.products | {item: inv.products.get(item, 0) + delta}
    else:
        setattr(inv, item, getattr(inv, item) + delta)


def evaluate(d):
    """A deliberately simplified material/geometry model, not real-world physics."""
    n = sum(p.count for p in d.parts)
    shape = Counter()
    for p in d.parts:
        shape[p.shape] += p.count
    strength = sum(MATERIALS[p.material]["strength"] * p.count for p in d.parts) / n
    burn = sum(MATERIALS[p.material]["burn"] * p.count for p in d.parts) / n
    insulation = sum(MATERIALS[p.material]["insulation"] * p.count for p in d.parts) / n
    seal = max((MATERIALS[p.material]["seal"] for p in d.parts if p.shape == "bowl"), default=0)
    joint = {"loose": 0.18, "fiber": 0.75, "clay": 0.5, "fitted": 0.85}[d.joint]
    support = min(1, strength * joint * 1.4)
    # Enclosure traps heat but an entirely sealed net cannot catch anything.
    catch = min(1, shape["mesh"] * 0.35 + shape["rod"] * 0.1) * joint * (0.25 if d.enclosed else 1)
    water = min(1, shape["bowl"]) * seal * joint * (1 if d.enclosed else 0.7)
    heat = (
        min(1, shape["bowl"] + shape["plate"] * 0.3)
        * insulation
        * (1 - burn)
        * (1 if d.enclosed else 0.4)
        * (1 if d.mechanism == "combustion" else 0.2)
    )
    cultivate = min(1, shape["blade"] * 0.45 + shape["rod"] * 0.1) * support
    if d.mechanism in ("lever", "rotary"):
        cultivate *= 1.3 if shape["rod"] else 0.3
    shelter = min(1, shape["plate"] * 0.3) * support * (1 if d.enclosed else 0.45)
    storage = min(1, shape["bowl"] * 0.5 + shape["plate"] * 0.15) * support
    measured = dict(
        zip(CAPABILITIES, (catch, water, heat, cultivate, shelter, storage), strict=True)
    )
    measured = {k: round(min(1, max(0, v)), 3) for k, v in measured.items()}
    feedback = []
    if joint < 0.4:
        feedback.append("Loose joints separated under load; change the connection.")
    if burn > 0.3 and d.mechanism == "combustion":
        feedback.append("Combustible walls lost heat and charred during the burn test.")
    if d.mechanism == "combustion" and not d.enclosed:
        feedback.append("The open chamber lost heat; enclosure may retain it.")
    if shape["mesh"] and d.enclosed:
        feedback.append("The enclosure obstructed the mesh opening.")
    if not feedback:
        feedback.append("Load, water retention, trapping and heating tests completed.")
    feedback.append("Measured effects: " + ", ".join(f"{k}={v:.2f}" for k, v in measured.items()))
    return measured, feedback


def propose(a, seed, tick, available, purpose):
    k = a.workshop
    if k and k.experiment:
        return k.experiment.model_copy(deep=True)
    tried = {design_id(t.design) for t in k.trials} if k else set()
    if k:
        for d in reversed(k.proposals):
            if design_id(d) not in tried and all(
                available.get(m, 0) >= n for m, n in cost(d).items()
            ):
                return d.model_copy(deep=True)
    materials = [m for m in MATERIALS if available.get(m, 0)]
    if not materials:
        return None
    rng = random.Random(f"{seed}:{a.id}:{tick // 18}:{purpose}:assemblies")
    empirical = max(k.trials, key=lambda t: t.measured.get(purpose, 0)) if k and k.trials else None
    choices = []
    for i in range(36):
        if empirical and i < 24:
            d = empirical.design.model_copy(deep=True)
            field = rng.choice(("parts", "joint", "mechanism", "enclosed"))
            if field == "parts":
                index = rng.randrange(len(d.parts))
                d.parts[index] = AssemblyPart(
                    material=rng.choice(materials),
                    shape=rng.choice(("plate", "rod", "bowl", "mesh", "wheel", "blade")),
                    count=rng.randint(1, 3),
                )
            elif field == "joint":
                d.joint = rng.choice(("loose", "fiber", "clay", "fitted"))
            elif field == "mechanism":
                d.mechanism = rng.choice(("passive", "lever", "rotary", "combustion"))
            else:
                d.enclosed = not d.enclosed
        else:
            d = AssemblyDesign(
                parts=[
                    AssemblyPart(
                        material=rng.choice(materials),
                        shape=rng.choice(("plate", "rod", "bowl", "mesh", "wheel", "blade")),
                        count=rng.randint(1, 3),
                    )
                    for _ in range(rng.randint(1, 3))
                ],
                joint=rng.choice(("loose", "fiber", "clay", "fitted")),
                mechanism=rng.choice(("passive", "lever", "rotary", "combustion")),
                enclosed=bool(rng.getrandbits(1)),
            )
        key = design_id(d)
        if key in tried or any(available.get(m, 0) < n for m, n in cost(d).items()):
            continue
        # Use actual past evidence only. Never evaluate unbuilt candidates here.
        similarity = 0
        if empirical:
            similarity = (
                sum(
                    getattr(d, f) == getattr(empirical.design, f)
                    for f in ("joint", "mechanism", "enclosed")
                )
                / 3
            )
        score = rng.random() * 0.3 + (
            empirical.measured.get(purpose, 0) * similarity if empirical else 0
        )
        d.name = f"{a.name}'s {purpose} experiment"
        choices.append((score, key, d))
    return max(choices, key=lambda c: c[:2])[2] if choices else None
