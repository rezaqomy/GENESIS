"""Curiosity and local needs propose experiments; no access to hidden physics scores."""

from app.simulation.actions.provisions import carrying_room
from app.simulation.engineering.invention import PURPOSES, best_tool, cost, design_id, propose
from app.simulation.models.domain import RESOURCE_KINDS, Action, Position, ToolDesign


def invention_goals(o, add, approach, supplies):
    a, t, k = o.self_agent, o.self_agent.personality, o.self_agent.inventions
    s = o.settlement
    communal = s is not None and a.position.distance(Position.model_validate(s["center"])) <= 8
    available = {
        material: getattr(a.inventory, material) + (s["storage"][material] if communal else 0)
        for material in RESOURCE_KINDS
    }
    needs = {
        "cut": 0.2 + 0.3 * any(r.kind == "wood" and r.quantity for r in o.resources),
        "mine": 0.2 + 0.3 * any(r.kind in ("stone", "ore") and r.quantity for r in o.resources),
        "light": 0.55 if o.environment.get("night") else 0.1,
    }
    purpose = max(PURPOSES, key=lambda p: (needs[p] - best_tool(a, p)[1], p))
    hypothesis = propose(a, o.seed, o.tick, available, purpose)
    peer_id = k.studying_peer if k and k.experiment else None
    if not (k and k.experiment):
        # Only actual tools carried by adjacent people are observable, not their notebooks.
        examples = [
            (peer["id"], ToolDesign.model_validate(tool["design"]))
            for peer in o.peers
            for tool in peer.get("tools", [])
            if not k or design_id(ToolDesign.model_validate(tool["design"])) not in k.designs
        ]
        if examples and t.sociability + t.curiosity > 0.8:
            peer_id, hypothesis = min(examples, key=lambda pair: (pair[0], design_id(pair[1])))
    ongoing = bool(k and k.experiment == hypothesis and k.experiment_steps > 0)
    recent = bool(k and k.trials and o.tick - k.trials[-1].tick < 18)
    ready = hypothesis is not None and (ongoing or supplies(cost(hypothesis), a.position))
    room = carrying_room(a.inventory, "tools") > 0
    # Curiosity keeps experiments available after a first successful discovery.
    factors = {
        "curiosity": t.curiosity * 0.36,
        "resourcefulness": t.resourcefulness * 0.15,
        "novelty": 0.18,
        "equipment_need": max(0, needs[purpose] - best_tool(a, purpose)[1]) * 0.3,
        "experiment_progress": 0.4 if ongoing else 0,
        "hunger_cost": -a.hunger / 100 * 0.2,
    }
    fires = [
        b
        for b in o.buildings
        if b["kind"] == "campfire"
        and b["progress"] == 100
        and b["durability"] > 0
        and b["fuel"] > 0
    ]
    if (
        ready
        and room
        and (ongoing or not recent)
        and hypothesis.fueled
        and fires
        and (not peer_id or ongoing)
    ):
        target = min(
            (Position.model_validate(b["position"]) for b in fires),
            key=lambda p: (a.position.distance(p), p.y, p.x),
        )
        approach(
            "experiment_tool",
            target,
            factors,
            Action.EXPERIMENT_TOOL,
            adjacent=True,
            tool_design=hypothesis,
            peer_id=peer_id,
        )
    else:
        add(
            "experiment_tool",
            factors,
            Action.EXPERIMENT_TOOL,
            rejection=(
                None
                if ready and room and (ongoing or not recent)
                else "Need local materials, carrying space, a new assembly, or recovery time"
            ),
            tool_design=hypothesis,
            peer_id=peer_id,
        )
    learned = [
        (key, trial)
        for key, trial in (k.designs.items() if k else [])
        if a.inventory.tools.get(key, 0) <= 0 and supplies(cost(trial.design), a.position)
    ]
    if learned and room:
        key, trial = max(
            learned, key=lambda pair: max(needs[p] * pair[1].performance[p] for p in PURPOSES)
        )
        add(
            "craft_tools",
            {"equipment_need": 0.4, "resourcefulness": t.resourcefulness * 0.2},
            Action.CRAFT,
            item=key,
            tool_design=trial.design.model_copy(),
        )
    else:
        add(
            "craft_tools",
            {},
            rejection="No personally tested design needing replacement or no materials/space",
        )
