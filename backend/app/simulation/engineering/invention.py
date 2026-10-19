"""Compositional tools: proposals use evidence; only real trials reveal performance."""

import hashlib
import random
from collections import Counter

from app.simulation.cognition.tiers import retain
from app.simulation.models.domain import MemoryRecord, ToolDesign, ToolKnowledge, ToolTrial

MATERIALS = {
    # Properties belong to the world. The proposer below never calls the test evaluator.
    "wood": {"hardness": 0.35, "burn": 0.75},
    "stone": {"hardness": 0.85, "burn": 0.0},
    "fiber": {"hardness": 0.08, "burn": 0.95},
    "clay": {"hardness": 0.22, "burn": 0.0},
    "ore": {"hardness": 0.95, "burn": 0.0},
}
PURPOSES = ("cut", "mine", "light")


def design_id(design):
    encoded = design.model_dump_json().encode()
    return "invention:" + hashlib.sha256(encoded).hexdigest()[:12]


def cost(design):
    result = Counter({design.core: 1})
    if design.grip != "none":
        result[design.grip] += design.length
    if design.binding != "none":
        result[design.binding] += 1
    if design.fueled:
        result["fuel"] += 1
    return dict(result)


def knowledge(agent):
    if agent.inventions is None:
        agent.inventions = ToolKnowledge()
    return agent.inventions


def best_tool(agent, purpose):
    legacy = {"cut": "axe", "mine": "pickaxe", "light": "torch"}[purpose]
    choices = [(legacy, 1.0)] if agent.inventory.tools.get(legacy, 0) > 0 else []
    if agent.inventions:
        choices += [
            (key, trial.performance.get(purpose, 0))
            for key, trial in agent.inventions.designs.items()
            if agent.inventory.tools.get(key, 0) > 0
        ]
    return max(choices, key=lambda pair: (pair[1], pair[0]), default=(None, 0.0))


def evaluate(design, practice, ignited=False):
    """Actual load/cutting/burning tests. No named-tool whitelist or recipe match."""
    hardness = MATERIALS[design.core]["hardness"]
    joint = {"none": 0.18, "clay": 0.38, "fiber": 0.88}[design.binding]
    leverage = 0.7 + design.length * 0.14
    control = 0.8 if design.grip in ("stone", "none") else 1.0
    if design.grip == "none":
        joint, leverage = 1.0, 0.7
    workmanship = 0.72 + min(0.28, practice / 180)
    edge = 1.0 if design.form == "edge" else 0.48 if design.form == "point" else 0.12
    point = 1.0 if design.form == "point" else 0.6 if design.form == "edge" else 0.18
    burn = MATERIALS[design.core]["burn"]
    flame = burn * (1 if design.form == "wrapped" else 0.32) * (1 if design.fueled else 0.08)
    if not ignited:
        flame = 0
    scores = {
        "cut": hardness * edge * joint * leverage * control * workmanship,
        "mine": hardness * point * joint * leverage * control * workmanship,
        "light": flame * (0.9 if design.grip == "wood" else 0.65) * workmanship,
    }
    scores = {key: round(min(1, max(0, value)), 4) for key, value in scores.items()}
    feedback = []
    if joint < 0.4:
        feedback.append("The head slipped under load; the joint needs reinforcement.")
    if hardness < 0.4:
        feedback.append("The working surface deformed against hard material.")
    if max(scores["cut"], scores["mine"]) < 0.3:
        feedback.append("The working shape removed little material in the test.")
    if design.fueled and scores["light"] < 0.3:
        feedback.append(
            "The assembly did not sustain a useful flame."
            if ignited
            else "There was no nearby ignition source for the burn test."
        )
    if max(scores.values()) >= 0.3:
        feedback.append("The prototype produced a useful measured effect; durability is limited.")
    return scores, feedback


def propose(agent, seed, tick, available, purpose):
    """Bounded search and mutation of personally observed trials, never oracle scores."""
    k = agent.inventions
    if k and k.experiment:
        return k.experiment.model_copy()
    seed_bytes = f"{seed}:{agent.id}:{tick // 12}:{purpose}".encode()
    rng = random.Random(int.from_bytes(hashlib.sha256(seed_bytes).digest()[:8]))
    cores = [m for m in MATERIALS if available.get(m, 0) > 0]
    grips = ["none"] + [m for m in ("wood", "stone", "fiber") if available.get(m, 0) > 0]
    if not cores:
        return None
    tried = {design_id(t.design) for t in k.trials} if k else set()
    empirical = (
        max(k.trials, key=lambda t: (t.performance.get(purpose, 0), t.tick))
        if k and k.trials
        else None
    )
    options = []
    fields = ("core", "grip", "binding", "form", "length", "fueled")
    mutation_fields = fields
    if empirical:
        evidence = " ".join(empirical.feedback)
        if "joint" in evidence:
            mutation_fields = ("binding", "grip")
        elif "deformed" in evidence:
            mutation_fields = ("core",)
        elif "sustain a useful flame" in evidence and purpose == "light":
            mutation_fields = ("core", "form", "fueled")
        elif "shape" in evidence:
            mutation_fields = ("form",)
    for index in range(48):
        values = {
            "core": rng.choice(cores),
            "grip": rng.choice(grips),
            "binding": rng.choice(["none"] + [m for m in ("fiber", "clay") if available.get(m, 0)]),
            "form": rng.choice(["rounded", "edge", "point", "wrapped"]),
            "length": rng.randint(1, 3),
            "fueled": bool(available.get("fuel", 0) and rng.getrandbits(1)),
        }
        if empirical and index < 32:
            # Small edits preserve measured progress; the rest explore unrelated assemblies.
            field = rng.choice(mutation_fields)
            values = empirical.design.model_dump() | {field: values[field]}
        if values["grip"] == "none":
            values["length"] = 1
        design = ToolDesign(**values)
        if design_id(design) in tried or any(
            available.get(m, 0) < n for m, n in cost(design).items()
        ):
            continue
        # Generalize only from this actor's measured features, with a novelty allowance.
        score = rng.random() * (0.12 + agent.personality.curiosity * 0.12)
        if empirical and index < 32:
            score += 0.15  # Prefer controlled revisions responding to witnessed failure.
        if k:
            for field in fields:
                evidence = [
                    t.performance[purpose]
                    for t in k.trials
                    if getattr(t.design, field) == getattr(design, field)
                ]
                mean = sum(evidence) / len(evidence) if evidence else 0
                score += (mean + 0.2 / (len(evidence) + 1) ** 0.5) / len(fields)
        options.append((score, design_id(design), design))
    return max(options, key=lambda item: item[:2])[2] if options else None


def validate(world, actor, intent):
    from app.simulation.actions.construction import affordable, materials
    from app.simulation.actions.provisions import carrying_room

    if actor.energy < 3:
        return "Not enough energy for tool work"
    if intent.tool_design is None:
        return "Tool work requires a physical design hypothesis"
    design = intent.tool_design
    key = design_id(design)
    k = actor.inventions
    ongoing = bool(
        intent.action.value == "EXPERIMENT_TOOL"
        and k
        and k.experiment == design
        and k.experiment_steps
        and k.studying_peer == intent.peer_id
    )
    if intent.action.value == "CRAFT":
        if not actor.inventions or key not in actor.inventions.designs:
            return "No personally tested tool design; experiment before crafting"
        if intent.item != key:
            return "Crafted item must match the tested design"
        if actor.inventory.tools.get(key, 0) > 0:
            return "This design is already equipped"
    if intent.peer_id and not ongoing:
        peer = world.agents.get(intent.peer_id)
        if not peer or not peer.alive or actor.position.distance(peer.position) > 1:
            return "Studying a tool requires a living adjacent maker"
        if (
            not peer.inventions
            or key not in peer.inventions.designs
            or peer.inventory.tools.get(key, 0) <= 0
        ):
            return "The peer is not carrying that real tool"
    if carrying_room(actor.inventory, "tools") <= 0 and actor.inventory.tools.get(key, 0) <= 0:
        return "No room for a prototype while preserving space for meals"
    if not ongoing:
        if not affordable(cost(design), materials(world, actor, actor.position)):
            return "Insufficient materials for this assembly"
    return None


def resolve(world, actor, intent):
    from app.simulation.actions.construction import materials, pay

    k = knowledge(actor)
    design = intent.tool_design
    copying = intent.action.value == "CRAFT"
    ongoing = (
        k.experiment == design and k.experiment_steps > 0 and k.studying_peer == intent.peer_id
    )
    if copying or not ongoing:
        pay(cost(design), materials(world, actor, actor.position))
    actor.energy = max(0, actor.energy - 3)
    k.practice += 1
    if not copying:
        if not ongoing:
            k.experiment, k.experiment_steps, k.studying_peer = (
                design.model_copy(),
                0,
                intent.peer_id,
            )
        k.experiment_steps += 1
        if k.experiment_steps < 3:
            return f"{actor.name} assembled and tested {design_id(design)} ({k.experiment_steps}/3)"
    ignited = any(
        b.kind == "campfire"
        and b.progress == 100
        and b.durability > 0
        and b.fuel > 0
        and actor.position.distance(b.position) <= 1
        for b in world.buildings.values()
    )
    performance, feedback = evaluate(design, k.practice, ignited=ignited)
    trial = ToolTrial(
        design=design.model_copy(),
        tick=world.tick + 1,
        performance=performance,
        feedback=feedback,
        source="craft" if copying else "study" if intent.peer_id else "experiment",
    )
    k.trials = [*k.trials, trial][-32:]
    key = design_id(design)
    useful = max(performance.values()) >= 0.3
    if useful:
        if key not in k.designs and len(k.designs) >= 24:
            # Forget an old, no-longer-carried design instead of forbidding new inventions.
            forgotten = min(
                (key for key in k.designs if actor.inventory.tools.get(key, 0) <= 0),
                key=lambda key: (k.designs[key].tick, key),
                default=None,
            )
            if forgotten:
                k.designs.pop(forgotten)
        k.designs[key] = trial.model_copy(deep=True)
        actor.inventory.tools[key] = max(4, round(12 + max(performance.values()) * 60))
    k.experiment, k.experiment_steps, k.studying_peer = None, 0, None
    text = (
        f"{actor.name} {'discovered a usable assembly' if useful else 'prototype failed'} "
        f"{key}: " + "; ".join(feedback)
    )
    retain(
        actor,
        MemoryRecord(
            id=f"invention:{actor.id}:{world.tick + 1}",
            tick=world.tick + 1,
            kind="reflection",
            text=text[:500],
            goal="experiment_tool",
            outcome=0.6 if useful else -0.3,
            importance=0.9,
            position=actor.position.model_copy(),
        ),
    )
    return text
