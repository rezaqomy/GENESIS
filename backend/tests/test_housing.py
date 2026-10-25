import pytest

from app.simulation.actions.resolver import resolve_intent
from app.simulation.engine.core import Engine
from app.simulation.engineering.housing import best_design, construction_cost, propose_design
from app.simulation.engineering.weathering import weather_damage
from app.simulation.events.reducer import agent_state, building_state, state_hash
from app.simulation.models.domain import (
    Action,
    Agent,
    AgentIntent,
    Building,
    DesignTrial,
    HousingKnowledge,
    Position,
    ShelterDesign,
    WorldConfig,
)
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy
from app.simulation.settlements.effects import local_effects


@pytest.fixture
def engine():
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    yield e
    store.close()


def learn(e, a, design=None):
    a.position = Position(x=1, y=0)
    design = design or ShelterDesign(
        frame="stone", roof="wood", bracing=True, raised_foundation=True
    )
    for _ in range(3):
        e.tick([AgentIntent(actor_id=a.id, action=Action.EXPERIMENT, design=design)])
    assert best_design(a) == design
    return design


def test_novice_cannot_build_by_naming_or_seeing_a_house(engine):
    a = engine.world.agents["agent-00"]
    a.position = Position(x=2, y=1)
    build = AgentIntent(
        actor_id=a.id, action=Action.BUILD, target=Position(x=2, y=2), building_kind="shelter"
    )
    assert resolve_intent(engine.world, build, engine.access) == (
        False,
        "No tested shelter design; experiment or study before building",
    )
    assert a.housing is None
    engine.world.buildings["visible"] = Building(
        id="visible",
        kind="shelter",
        position=Position(x=3, y=1),
        progress=100,
        design=ShelterDesign(),
        quality=0.4,
    )
    assert not resolve_intent(engine.world, build, engine.access)[0]
    assert a.housing is None


def test_experiment_consumes_materials_once_requires_three_work_actions_and_can_fail(engine):
    a = engine.world.agents["agent-00"]
    a.position = Position(x=1, y=0)
    s = engine.world.settlements[a.settlement_id]
    design = ShelterDesign()
    intent = AgentIntent(actor_id=a.id, action=Action.EXPERIMENT, design=design)
    initial = s.storage.wood
    for i in range(3):
        engine.tick([intent])
        assert s.storage.wood == initial - 1
        if i < 2:
            assert not a.housing.trials and best_design(a) is None
    assert len(a.housing.trials) == 1
    assert not a.housing.trials[-1].stood
    assert best_design(a) is None
    assert a.housing.practice == 3
    assert any("prototype failed" in m.text for m in a.memory.long_term)
    assert state_hash(engine.store.replay(engine.run_id)) == state_hash(engine.world)


def test_learned_design_materials_quality_and_practice_affect_real_building(engine):
    a = engine.world.agents["agent-00"]
    design = learn(engine, a)
    a.position = Position(x=2, y=1)
    s = engine.world.settlements[a.settlement_id]
    cost = construction_cost("shelter", design)
    for key in cost:
        setattr(s.storage, key, 20)
    prior = s.storage.model_copy()
    intent = AgentIntent(
        actor_id=a.id,
        action=Action.BUILD,
        target=Position(x=2, y=2),
        building_kind="shelter",
        design=design,
    )
    for _ in range(4):
        engine.tick([intent])
    b = engine.world.buildings["building:2:2"]
    assert b.progress == 100 and b.design == design
    assert 0.1 < b.quality < 0.7 and b.durability < 100
    assert b.work_units == 4 and b.contributors == [a.id]
    for key, amount in cost.items():
        assert getattr(s.storage, key) == getattr(prior, key) - amount
    assert 0 < local_effects(engine.world, b.position)["comfort"] < 0.7
    assert a.housing.practice == 11
    assert state_hash(engine.store.replay(engine.run_id)) == state_hash(engine.world)


def test_same_design_is_built_better_after_real_practice(engine):
    from app.simulation.engineering.housing import workmanship

    a = engine.world.agents["agent-00"]
    design = learn(engine, a)
    novice = workmanship(a, design, 42, 10, "identical-test")
    a.housing.practice = 60
    practiced = workmanship(a, design, 42, 10, "identical-test")
    assert practiced > novice + 0.3


def test_study_is_local_and_does_not_instantly_copy_a_design(engine):
    a = engine.world.agents["agent-00"]
    design = ShelterDesign(frame="stone", roof="wood", bracing=True, raised_foundation=True)
    b = Building(
        id="teacher",
        kind="shelter",
        position=Position(x=4, y=0),
        progress=100,
        quality=0.85,
        design=design,
    )
    engine.world.buildings[b.id] = b
    intent = AgentIntent(actor_id=a.id, action=Action.EXPERIMENT, building_id=b.id, design=design)
    a.position = Position(x=40, y=0)
    assert not resolve_intent(engine.world, intent, engine.access)[0]
    a.position = Position(x=3, y=0)
    for i in range(3):
        assert resolve_intent(engine.world, intent, engine.access)[0]
        if i < 2:
            assert best_design(a) is None
    assert best_design(a) == design
    assert a.housing.trials[-1].source == "study"
    assert a.housing.practice == 3


def test_storm_collapses_weak_house_strong_house_survives_and_only_witnesses_learn(engine):
    w = engine.world
    a, remote = w.agents["agent-00"], w.agents["agent-01"]
    a.position = Position(x=2, y=1)
    remote.position = Position(x=60, y=60)
    design = ShelterDesign()
    a.housing = HousingKnowledge(trials=[DesignTrial(design=design, tick=0, score=0.3, stood=True)])
    weak = Building(
        id="weak",
        kind="shelter",
        position=Position(x=2, y=2),
        progress=100,
        durability=40,
        quality=0.2,
        design=design,
        owner_id=remote.id,
    )
    strong = Building(
        id="strong",
        kind="shelter",
        position=Position(x=20, y=2),
        progress=100,
        quality=0.95,
        design=ShelterDesign(frame="stone", roof="wood", bracing=True, raised_foundation=True),
    )
    w.buildings.update({weak.id: weak, strong.id: strong})
    env = {"weather": "storm", "wind_strength": 0.95}
    events = []
    for tick in (12, 24, 36):
        events += weather_damage(w, tick, env)
    assert weak.durability == 0
    assert strong.durability >= 95
    assert any(kind == "BUILDING_COLLAPSED" for kind, _ in events)
    assert "bracing" in a.housing.insights
    assert a.housing.trials[0].score < 0.3
    assert propose_design(a, 42, 37).bracing
    assert remote.housing is None  # Ownership is not remote knowledge.
    from app.simulation.engineering.weathering import observe_ruins

    remote.position = weak.position.model_copy()
    observe_ruins(w, remote, 37, 8)
    assert "bracing" in remote.housing.insights
    observed = len(remote.memory.long_term)
    observe_ruins(w, remote, 38, 8)
    assert len(remote.memory.long_term) == observed
    assert local_effects(w, weak.position)["comfort"] == 0


def test_new_fields_preserve_old_after_images(engine):
    a = agent_state(engine.world.agents["agent-00"])
    a.pop("housing", None)
    assert agent_state(Agent.model_validate(a)) == a
    old = {
        "id": "old",
        "kind": "shelter",
        "position": {"x": 2, "y": 2},
        "settlement_id": None,
        "owner_id": None,
        "progress": 100,
        "durability": 100,
        "fuel": 0,
        "food": 0,
        "created_tick": 0,
    }
    assert building_state(Building.model_validate(old)) == old


def test_engine_records_storm_damage_and_replays_learning(engine, monkeypatch):
    from app.simulation.settlements import environment

    a = engine.world.agents["agent-00"]
    design = learn(engine, a)
    a.position = Position(x=2, y=1)
    s = engine.world.settlements[a.settlement_id]
    for key in construction_cost("shelter", design):
        setattr(s.storage, key, 20)
    build = AgentIntent(
        actor_id=a.id,
        action=Action.BUILD,
        target=Position(x=2, y=2),
        building_kind="shelter",
        design=design,
    )
    for _ in range(4):
        engine.tick([build])
    actual_conditions = environment.conditions
    monkeypatch.setattr(
        environment,
        "conditions",
        lambda seed, tick: actual_conditions(seed, tick)
        | {"weather": "storm", "wind_strength": 0.99},
    )
    events = []
    for _ in range(53):
        events += engine.tick([AgentIntent(actor_id=a.id, action=Action.REST)])
    assert any(e.event_type == "BUILDING_DAMAGED" for e in events)
    assert any(e.event_type == "BUILDING_COLLAPSED" for e in events)
    assert a.housing.observed_failures
    assert state_hash(engine.store.replay(engine.run_id)) == state_hash(engine.world)
    assert state_hash(engine.store.replay(engine.run_id, use_snapshot=True)) == state_hash(
        engine.world
    )
