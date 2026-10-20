"""Typed Laya choices over bounded, human-readable local observations."""

from app.simulation.cognition.tiers import memory_context

GOALS = {
    "plant_crop": "Try growing a seed in local soil, preparing the ground if necessary.",
    "gather_seed": "Gather visible seeds for planting and feeding animals.",
    "water_crop": "Water a thirsty crop using carried water.",
    "supply_crop_water": "Collect visible water for a thirsty crop.",
    "harvest_crop": "Harvest a ripe crop into food and seeds.",
    "make_harvest_space": "Free carrying room for a visible ripe crop before harvesting.",
    "clear_crop": "Clear a failed crop before planting again.",
    "tend_animal": "Feed a nearby animal to earn trust and keep it alive.",
    "breed_animals": "Breed two personally tamed, fed adult animals.",
    "collect_animal": "Collect supplies from a fed tame adult animal.",
    "hunt_food": "Hunt a visible wild animal for food, then recover its dropped supplies.",
    "recover_food": "Pick up visible dropped food before it decays.",
    "recover_supplies": "Recover real dropped materials or a worn tool.",
    "defend_self": "Defend yourself against a recent local attacker.",
    "flee_attack": "Escape a local attacker when injured or exhausted.",
    "steal_to_survive": "Risk taking food from a nearby peer when desperate; harms trust.",
    "experiment_assembly": "Invent a device from parts, or test an idea heard in conversation.",
    "supply_assembly": "Physically collect the materials for a tested device before building it.",
    "fabricate_assembly": "Fabricate a personally tested useful device at a suitable local site.",
    "operate_catch": "Use a working trap to catch food beside water.",
    "operate_water": "Use a working container to collect water for farming.",
    "operate_cultivate": "Use a working implement, seeds and water to cultivate food.",
    "heat_material": "Test or repeat a material transformation using local heat and fuel.",
    "barter": "Offer a physical exchange, or accept an offer addressed to you.",
    "mine_building_material": "Extract local rock with a personally tested mining tool.",
    "prepare_farmland": "Place carried earth near camp to prepare a fertile farm site.",
    "help_neighbor": "Give a spare meal to a visibly hungry or injured neighbour.",
    "feed_community": "Gather and deliver meals to the public food reserve.",
    "organize_project": "Post a locally needed shared building project at the meeting place.",
    "maintain_community": "Repair a damaged standing structure before it collapses.",
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
    board = (observation.settlement or {}).get("community") or {}
    project = next((p for p in board.get("projects", []) if p["status"] == "active"), None)
    notice = {k: project[k] for k in ("kind", "target", "cost")} if project else None
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
    workshop_evidence = [
        {"name": t.design.name, "measured": t.measured}
        for t in (a.workshop.trials[-2:] if a.workshop else [])
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
        f"Local animals: {observation.animals[:4]}. Local crops: {observation.crops[:4]}. "
        f"Local dropped supplies: {observation.drops[:2]}. "
        f"Vision range {observation.vision_radius} grid tiles; unseen places are unknown. "
        f"Tool trial evidence: {tool_evidence}. "
        f"Workshop trials: {workshop_evidence}. "
        f"Untested ideas heard: {[d.name for d in (a.workshop.proposals if a.workshop else [])]}. "
        f"Tool experiment progress: {a.inventions.experiment_steps if a.inventions else 0}/3. "
        f"Relevant experiences: {'; '.join(m['text'][:120] for m in episodes)}. "
        f"Observed food (may be stale): {memory['food_facts']}. "
        f"Practical lessons: {memory['lessons']}. "
        f"Current task: {memory['task']}. Verified skills: {memory['verified_skills']}. "
        f"Learned preferences: {a.habits}. "
        f"Shelter experiments: {len(a.housing.trials) if a.housing else 0}; "
        f"observed construction lessons: {a.housing.insights if a.housing else []}. "
        f"Community food reserves: "
        f"{(observation.settlement or {}).get('food_reserves', 'unknown (outside sight)')}. "
        f"Local public project: {notice}."
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
