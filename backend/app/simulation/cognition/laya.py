"""Typed Laya choices over bounded, human-readable local observations."""

from app.simulation.cognition.tiers import memory_context

GOALS = {
    "make_food_space": "Abandon surplus materials to carry life-saving meals.",
    "supply_farm": "Bring water to a visible community farm to keep food growing.",
    "experiment_shelter": "Test materials and joints or study a nearby structure.",
    "experiment_tool": (
        "Invent an assembly: test materials, shapes and joints, or study a nearby real tool; "
        "learn from failures and improve designs."
    ),
    "eat": "Eat carried food to relieve hunger.",
    "rest": "Recover energy and reduce exhaustion.",
    "find_food": "Find and gather food; search new local terrain when known patches are depleted.",
    "return_home": "Return home for comfort, company or resupply.",
    "socialize": "Spend time with a visible companion to relieve loneliness.",
    "seek_safety": "Seek protection from fear, exposure or danger.",
    "explore": "Explore unknown places out of curiosity, independence or scarcity.",
    "take_shared_food": "Withdraw food from community supplies when hungry.",
    "improve_settlement": "Build community structures for shared comfort and productivity.",
    "take_materials": "Withdraw community materials for a construction project.",
    "share_food": "Contribute spare food to help the community.",
    "store_resources": "Store carried resources for the community.",
    "gather_resources": "Gather materials for crafting and construction.",
    "craft_tools": "Craft a useful tool to work more effectively.",
    "build_shelter": "Build shelter for comfort and protection.",
    "refuel": "Refuel the fire for warmth.",
    "establish_camp": "Build a camp away from home.",
}


def request(observation, goals):
    a = observation.self_agent
    traits = ", ".join(f"{k}={v:.1f}" for k, v in a.personality.model_dump().items())
    feelings = ", ".join(f"{k}={v:.1f}" for k, v in a.psychology.model_dump().items())
    memory = memory_context(a, observation.tick, observation.environment, a.decision.selected_goal)
    episodes = memory["recalled"] or memory["legacy_recent"]
    tool_evidence = [
        {
            "design": trial.design.model_dump(),
            "measured": trial.performance,
            "feedback": trial.feedback,
        }
        for trial in (a.inventions.trials[-2:] if a.inventions else [])
    ]
    state = (
        f"Villager {a.name}. Hunger {a.hunger}/100 (100=starving), energy {a.energy}/100, "
        f"health {a.health}/100. Carried food {a.inventory.food}, "
        f"inventory {a.inventory.total}/{a.inventory.capacity}. "
        f"Home distance {a.position.distance(a.home)} tiles. "
        f"Personality (0..1): {traits}. Feelings (0..1): {feelings}. "
        f"Weather {observation.environment.get('weather')}; "
        f"night={observation.environment.get('night')}. "
        f"Visible companions {len(observation.peers)}. "
        f"Vision range {observation.vision_radius} grid tiles; unseen places are unknown. "
        f"Tool trial evidence: {tool_evidence}. "
        f"Tool experiment progress: {a.inventions.experiment_steps if a.inventions else 0}/3. "
        f"Relevant experiences: {'; '.join(m['text'][:120] for m in episodes)}. "
        f"Observed food (may be stale): {memory['food_facts']}. "
        f"Practical lessons: {memory['lessons']}. "
        f"Current task: {memory['task']}. Verified skills: {memory['verified_skills']}. "
        f"Learned preferences: {a.habits}. "
        f"Shelter experiments: {len(a.housing.trials) if a.housing else 0}; "
        f"observed construction lessons: {a.housing.insights if a.housing else []}. "
        f"Community food reserves: "
        f"{(observation.settlement or {}).get('food_reserves', 'unknown (outside sight)')}."
    )
    return {"state": state, "criteria": {g: GOALS.get(g, g.replace("_", " ")) for g in goals}}


def decode(result, settings):
    from app.simulation.cognition.runtime import Choice

    if result["model"] != settings.laya_model or result.get("device") != "cpu":
        raise ValueError("Unexpected local Laya model or device")
    probability = float(result["probability"])
    if not 0 <= probability <= 1:
        raise ValueError("Invalid Laya probability")
    goal = result["goal"]
    # This describes the typed result; Laya does not generate a chain of thought.
    return Choice(goal=goal, reason=f"Laya choice: {goal}; probability {probability:.3f}.")


async def choose(client, settings, observation, goals):
    response = await client.post(settings.laya_url + "/decide", json=request(observation, goals))
    response.raise_for_status()
    return decode(response.json(), settings)


async def choose_batch(client, settings, observations, baselines):
    requests = [
        request(o, [c.goal for c in b.decision.candidates if not c.rejection])
        for o, b in zip(observations, baselines, strict=True)
    ]
    response = await client.post(settings.laya_url + "/decide-batch", json={"requests": requests})
    response.raise_for_status()
    results = response.json()["results"]
    if len(results) != len(requests):
        raise ValueError("Laya batch response length mismatch")
    choices = [decode(r, settings) for r in results]
    if any(c.goal not in r["criteria"] for c, r in zip(choices, requests, strict=True)):
        raise ValueError("Laya selected an unavailable goal")
    return choices
