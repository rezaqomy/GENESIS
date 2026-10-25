import json

import pytest

from app.simulation.actions.resolver import resolve_intent
from app.simulation.engine.core import Engine
from app.simulation.engineering import invention
from app.simulation.events.reducer import agent_state, authoritative_state, state_hash
from app.simulation.models.domain import (
    Action,
    Agent,
    AgentIntent,
    Position,
    TaskPlan,
    ToolDesign,
    WorldConfig,
)
from app.simulation.observation.builder import build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.projects import propose_project
from app.simulation.policies.utility import UtilityPolicy


@pytest.fixture
def engine():
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    yield e
    store.close()


def trial(e, a, design, peer_id=None):
    intent = AgentIntent(
        actor_id=a.id, action=Action.EXPERIMENT_TOOL, tool_design=design, peer_id=peer_id
    )
    for _ in range(3):
        assert resolve_intent(e.world, intent, e.access)[0]
    return invention.design_id(design)


def strong_design():
    return ToolDesign(core="stone", grip="wood", binding="fiber", form="edge", length=3)


def test_naming_a_tool_or_supplying_an_untested_design_does_not_unlock_crafting(engine):
    a = engine.world.agents["agent-00"]
    a.position = Position(x=1, y=0)
    for name in ("axe", "pickaxe", "torch"):
        assert not resolve_intent(
            engine.world, AgentIntent(actor_id=a.id, action=Action.CRAFT, item=name), engine.access
        )[0]
    d = strong_design()
    assert not resolve_intent(
        engine.world,
        AgentIntent(actor_id=a.id, action=Action.CRAFT, item=invention.design_id(d), tool_design=d),
        engine.access,
    )[0]
    assert a.inventions is None and not a.inventory.tools


def test_real_failed_trial_costs_once_records_evidence_and_replays(engine):
    a = engine.world.agents["agent-00"]
    a.position = Position(x=1, y=0)
    d = ToolDesign(core="wood", grip="wood")
    s = engine.world.settlements[a.settlement_id].storage
    before = s.wood
    intent = AgentIntent(actor_id=a.id, action=Action.EXPERIMENT_TOOL, tool_design=d)
    for step in range(3):
        engine.tick([intent])
        assert s.wood == before - 2
        if step < 2:
            assert not a.inventions.trials and not a.inventory.tools
    assert len(a.inventions.trials) == 1
    assert not a.inventions.designs and not a.inventory.tools
    assert any("joint" in text for text in a.inventions.trials[0].feedback)
    assert any("prototype failed" in m.text for m in a.memory.long_term)
    assert state_hash(engine.world) == state_hash(engine.store.replay(engine.run_id))


def test_composition_can_have_multiple_real_uses_and_be_recreated_after_wear(engine):
    a = engine.world.agents["agent-00"]
    a.position = Position(x=1, y=0)
    d = strong_design()
    key = trial(engine, a, d)
    assert key.startswith("invention:")
    assert invention.best_tool(a, "cut")[1] >= 0.3
    assert invention.best_tool(a, "mine")[1] >= 0.3
    # Physically gather wood with the invented design, not a whitelisted axe name.
    resource = next(
        r
        for r in engine.access.visible_resources(a.position, 8)
        if r.kind == "wood" and r.quantity >= 2
    )
    a.position = resource.position.model_copy()
    before, durability = a.inventory.wood, a.inventory.tools[key]
    assert resolve_intent(
        engine.world,
        AgentIntent(actor_id=a.id, action=Action.GATHER, resource_id=resource.id),
        engine.access,
    )[0]
    assert a.inventory.wood == before + 2 and a.inventory.tools[key] == durability - 1
    a.position = Position(x=1, y=0)
    a.inventory.tools[key] = 0
    copy = AgentIntent(actor_id=a.id, action=Action.CRAFT, item=key, tool_design=d)
    assert resolve_intent(engine.world, copy, engine.access)[0]
    assert a.inventory.tools[key] > 0
    assert not resolve_intent(engine.world, copy, engine.access)[0]


def test_study_requires_adjacent_real_tool_and_personal_paid_trials(engine):
    maker, observer = engine.world.agents["agent-00"], engine.world.agents["agent-01"]
    maker.position = Position(x=1, y=0)
    d = strong_design()
    key = trial(engine, maker, d)
    observer.position = Position(x=5, y=0)
    o = build_observation(engine.world, observer.id, access=engine.access)
    assert next(p for p in o.peers if p["id"] == maker.id)["tools"] == []
    intent = AgentIntent(
        actor_id=observer.id, action=Action.EXPERIMENT_TOOL, tool_design=d, peer_id=maker.id
    )
    assert not resolve_intent(engine.world, intent, engine.access)[0]
    observer.position = Position(x=2, y=0)
    o = build_observation(engine.world, observer.id, access=engine.access)
    assert next(p for p in o.peers if p["id"] == maker.id)["tools"][0]["design"] == d.model_dump()
    assert observer.inventions is None
    for step in range(3):
        assert resolve_intent(engine.world, intent, engine.access)[0]
        if step < 2:
            assert not observer.inventions.designs
    assert key in observer.inventions.designs
    assert observer.inventions.trials[-1].source == "study"
    maker.inventory.tools[key] = 0
    assert not resolve_intent(engine.world, intent, engine.access)[0]


def test_proposals_use_personal_evidence_without_testing_hypotheses_for_free(engine, monkeypatch):
    a = engine.world.agents["agent-00"]
    a.position = Position(x=1, y=0)
    trial(engine, a, strong_design())
    before = a.model_dump_json()
    monkeypatch.setattr(
        invention, "evaluate", lambda *args: pytest.fail("Oracle used during planning")
    )
    available = {m: 8 for m in ("wood", "stone", "fiber", "clay", "ore", "fuel")}
    proposals = [invention.propose(a, 42, tick, available, "mine") for tick in range(0, 120, 12)]
    assert all(p and invention.design_id(p) not in a.inventions.designs for p in proposals)
    assert len({invention.design_id(p) for p in proposals}) > 3
    assert a.model_dump_json() == before


def test_explicit_valid_model_goal_can_interrupt_commitment_and_old_task(engine):
    a = engine.world.agents["agent-00"]
    a.position = Position(x=1, y=0)
    a.inventory.food = 1
    a.decision.selected_goal = "return_home"
    a.decision.commitment_until = 50
    a.task = TaskPlan(
        id="old",
        kind="forage",
        context="day:safe",
        stage="acquire",
        started_tick=0,
        last_progress_tick=0,
        deadline=120,
        origin=a.position.model_copy(),
    )
    o = build_observation(engine.world, a.id, access=engine.access)
    intent = engine.policy.decide(o, preferred_goal="experiment_tool")
    assert intent.decision.selected_goal == "experiment_tool"
    assert intent.action == Action.EXPERIMENT_TOOL
    assert resolve_intent(engine.world, intent, engine.access)[0]
    a.hunger = 95
    o = build_observation(engine.world, a.id, access=engine.access)
    assert engine.policy.decide(o, preferred_goal="experiment_tool").action == Action.EAT


def test_new_knowledge_preserves_old_serialization_and_snapshot_replay(engine):
    a = engine.world.agents["agent-00"]
    old = agent_state(a)
    old.pop("inventions", None)
    assert agent_state(Agent.model_validate(old)) == old
    a.position = Position(x=1, y=0)
    # Record the manually configured scenario before testing full replay.
    engine.store.append(
        [engine.event("WORLD_CREATED", {"state": authoritative_state(engine.world)})], engine.world
    )
    intent = AgentIntent(actor_id=a.id, action=Action.EXPERIMENT_TOOL, tool_design=strong_design())
    for _ in range(3):
        engine.tick([intent])
    for snapshot in (False, True):
        assert state_hash(engine.world) == state_hash(
            engine.store.replay(engine.run_id, use_snapshot=snapshot)
        )
    assert json.loads(a.inventions.model_dump_json())["designs"]


def test_project_sites_are_visible_valid_and_food_need_can_change_priority(engine):
    a = engine.world.agents["agent-00"]
    a.position = Position(x=1, y=0)
    a.personality.cooperation = 1
    a.personality.comfort_preference = 0
    o = build_observation(engine.world, a.id, access=engine.access)
    o.local_effects["comfort"] = 1
    o.settlement["food_reserves"] = 0
    kind, target, _ = propose_project(o)
    assert kind == "farm"
    assert target in [tile.position for tile in o.tiles]
    assert engine.access.tile(target).terrain.value in ("grass", "soil")


def test_burn_test_needs_real_ignition_and_light_has_a_world_effect(engine):
    a = engine.world.agents["agent-00"]
    d = ToolDesign(core="fiber", grip="wood", binding="fiber", form="wrapped", fueled=True)
    # A warm-looking assembly does not spontaneously create fire away from ignition.
    a.position = Position(x=30, y=0)
    a.inventory.fiber, a.inventory.wood, a.inventory.fuel = 6, 4, 4
    trial(engine, a, d)
    assert not a.inventions.designs
    assert any("ignition" in text for text in a.inventions.trials[-1].feedback)
    a.position = Position(x=1, y=0)
    from app.simulation.settlements.effects import local_effects

    # Isolate the light's effect from the campfire that ignites it.
    key = trial(engine, a, d)
    a.position = Position(x=30, y=0)
    before = local_effects(engine.world, a.position)["warmth"]
    assert before >= 0.2
    a.inventory.tools[key] = 0
    assert local_effects(engine.world, a.position)["warmth"] < before


def test_tool_work_preserves_meal_space_and_rejects_without_spending(engine):
    a = engine.world.agents["agent-00"]
    a.position = Position(x=1, y=0)
    a.inventory.wood = 21
    d = strong_design()
    before = authoritative_state(engine.world)
    accepted, message = resolve_intent(
        engine.world,
        AgentIntent(actor_id=a.id, action=Action.EXPERIMENT_TOOL, tool_design=d),
        engine.access,
    )
    assert not accepted and "meals" in message
    assert authoritative_state(engine.world) == before
