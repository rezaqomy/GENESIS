from app.simulation.cognition.laya import request
from app.simulation.cognition.memory import experience
from app.simulation.cognition.tiers import (
    action_outcome,
    action_snapshot,
    avoided_tiles,
    food_destinations,
    goal_adjustment,
    learn,
    memory_context,
    observe_food,
    retain,
    retrieve,
)
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import agent_state, state_hash
from app.simulation.models.domain import (
    Action,
    Agent,
    AgentIntent,
    AgentMemory,
    Decision,
    MemoryRecord,
    Position,
    Resource,
    Terrain,
    Tile,
    WorldConfig,
)
from app.simulation.observation.builder import Observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


def actor():
    return Agent(
        id="agent-00", name="Ada", age=25, visual_color="#fff", position=Position(x=0, y=0)
    )


def record(tick, **kwargs):
    return MemoryRecord(
        **(
            dict(
                id=f"event:{tick}",
                tick=tick,
                kind="action",
                text="A useful experience",
                goal="rest",
                action="REST",
                context="day:safe",
                outcome=0.6,
                importance=0.8,
                position=Position(x=0, y=0),
            )
            | kwargs
        )
    )


def test_short_expiry_long_retention_and_bounded_growth():
    a = actor()
    retain(a, record(1, text="Important event", importance=1))
    for tick in range(2, 101):
        retain(a, record(tick, importance=0.1))
    assert len(a.memory.short_term) == 24
    assert all(m.tick >= 77 for m in a.memory.short_term)
    assert a.memory.long_term[0].text == "Important event"
    assert any(m.tick == 1 for m in retrieve(a, 100, {"night": False}, "rest"))
    for tick in range(101, 201):
        retain(a, record(tick))
    assert len(a.memory.long_term) == 64
    observe_food(a, [], 300)
    assert not a.memory.short_term


def test_retrieval_prefers_relevance_deduplicates_and_does_not_mutate():
    a = actor()
    retain(a, record(1, goal="find_food", importance=1))
    for tick in range(2, 15):
        retain(a, record(tick, goal="socialize", importance=0.2))
    before = a.model_dump_json()
    result = retrieve(a, 15, {"night": False}, "find_food")
    assert result[0].goal == "find_food"
    assert len({m.id for m in result}) == len(result) == 6
    assert retrieve(a, 15, {}, limit=0) == []
    assert a.model_dump_json() == before


def test_food_facts_update_depletion_forget_stale_and_never_infer_regeneration():
    a = actor()
    food = Resource(
        id="r:2:0:food", kind="food", position=Position(x=2, y=0), quantity=4, capacity=4
    )
    observe_food(a, [food], 1)
    assert food_destinations(a, 2) == [food.position]
    food.quantity = 0
    observe_food(a, [food], 3)
    assert not food_destinations(a, 4)
    assert not food_destinations(a, 23)  # No unseen regeneration assumed.
    food.quantity = 2
    observe_food(a, [food], 24)
    assert food_destinations(a, 25)
    assert not food_destinations(a, 265)
    observe_food(a, [], 265)
    assert not a.memory.facts
    resources = [
        food.model_copy(update={"id": f"food:{i}", "position": Position(x=i, y=0)})
        for i in range(100)
    ]
    observe_food(a, resources, 266)
    assert len(a.memory.facts) == 64


def test_local_repeated_failures_expire_without_goal_aversion():
    a = actor()
    for tick in (1, 2):
        r = record(
            tick,
            kind="failure",
            action="MOVE",
            goal="find_food",
            outcome=-0.8,
            text="Target tile is occupied",
            target=Position(x=1, y=0),
        )
        retain(a, r)
        learn(a, r)
    assert avoided_tiles(a, 2) == {(1, 0)}
    assert not avoided_tiles(a, 9)
    assert goal_adjustment(a, "find_food", 2, {"night": False}) == 0
    assert not a.memory.lessons


def test_actual_effects_reward_eating_but_not_saturated_rest_or_idle():
    a = actor()
    a.hunger = 90
    before = action_snapshot(a)
    a.hunger = 55
    assert action_outcome(a, AgentIntent(actor_id=a.id, action=Action.EAT), True, before) == 1
    assert action_outcome(a, AgentIntent(actor_id=a.id, action=Action.REST), True, before) == 0
    assert action_outcome(a, AgentIntent(actor_id=a.id, action=Action.IDLE), True, before) == 0
    assert action_outcome(a, AgentIntent(actor_id=a.id, action=Action.EAT), False, before) < 0


def decision_observation(a, tick=10):
    a.energy, a.hunger, a.inventory.food = 70, 0, 3
    a.personality.comfort_preference = 0
    a.personality.sociability = 0
    a.personality.loyalty = 0
    a.personality.curiosity = 0.15
    a.personality.independence = 0
    a.personality.exploration_drive = 0
    a.personality.risk_tolerance = 1
    return Observation(
        seed=42,
        path_budget=2000,
        tick=tick,
        self_agent=a,
        environment={"night": False},
        tiles=[
            Tile(position=Position(x=x, y=y), terrain=Terrain.GRASS, walkable=True)
            for x in range(-8, 9)
            for y in range(-8, 9)
        ],
        resources=[],
        occupied=[],
    )


def test_learned_outcomes_change_real_goal_choice_and_respect_context_and_survival():
    a = actor()
    policy = UtilityPolicy()
    o = decision_observation(a)
    baseline = policy.decide(o)
    # Rest and exploration have similar utility in this controlled world.
    assert baseline.decision.selected_goal == "rest"
    for tick in range(1, 6):
        learn(a, record(tick, outcome=-1))
    learned = policy.decide(o)
    assert learned.decision.selected_goal == "explore"
    assert (
        next(c for c in learned.decision.candidates if c.goal == "rest").factors["memory_outcome"]
        < 0
    )
    assert goal_adjustment(a, "rest", 10, {"night": True}) == 0
    assert abs(goal_adjustment(a, "rest", 1000, {"night": False})) < abs(
        goal_adjustment(a, "rest", 10, {"night": False})
    )
    assert any(m.kind == "reflection" for m in a.memory.long_term)
    a.hunger, a.inventory.food = 95, 1
    assert policy.decide(o, preferred_goal="explore").action == Action.EAT


def test_movement_uses_failure_memory_for_an_alternative_first_step():
    a = actor()
    o = decision_observation(a)
    food = Resource(
        id="r:3:0:food", kind="food", position=Position(x=3, y=0), quantity=4, capacity=4
    )
    a.hunger, a.inventory.food = 90, 0
    o.resources = [food]
    policy = UtilityPolicy()
    assert policy.decide(o).target == Position(x=1, y=0)
    for tick in (8, 9):
        retain(
            a,
            record(
                tick,
                kind="failure",
                action="MOVE",
                text="Target tile is occupied",
                target=Position(x=1, y=0),
            ),
        )
    alternative = policy.decide(o)
    assert alternative.action == Action.MOVE
    assert alternative.target != Position(x=1, y=0)
    assert alternative.decision.selected_goal == "find_food"


def test_model_context_contains_relevant_long_term_memory_and_is_bounded():
    a = actor()
    o = decision_observation(a, 100)
    a.decision.selected_goal = "rest"
    retain(a, record(1, text="Old important experience"))
    for tick in range(2, 100):
        retain(a, record(tick, importance=0.1, goal="explore"))
    before = a.model_dump_json()
    context = memory_context(a, 100, o.environment, "rest")
    assert any(m["text"] == "Old important experience" for m in context["recalled"])
    assert len(context["recalled"]) <= 6
    assert "Old important experience" in request(o, ["rest"])["state"]
    assert a.model_dump_json() == before


def test_legacy_field_presence_and_roundtrip():
    a = actor()
    legacy = agent_state(a)
    assert "memory" not in legacy
    assert agent_state(Agent.model_validate(legacy)) == legacy
    retain(a, record(1))
    assert agent_state(Agent.model_validate(agent_state(a))) == agent_state(a)
    assert isinstance(Agent.model_validate_json(a.model_dump_json()).memory, AgentMemory)


def test_layers_persist_across_full_replay_snapshot_and_restart(tmp_path):
    path = str(tmp_path / "memory.sqlite")
    store = EventStore(path)
    engine = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    run_id = engine.run_id
    for _ in range(27):
        engine.tick()
    a = engine.world.agents["agent-00"]
    assert a.memory.short_term and a.memory.facts and a.memory.lessons
    expected = state_hash(engine.world)
    assert state_hash(store.replay(run_id, use_snapshot=False)) == expected
    assert state_hash(store.replay(run_id, use_snapshot=True)) == expected
    store.close()
    store = EventStore(path)
    restored = Engine(WorldConfig(infinite=True), store, UtilityPolicy(), restore=True)
    assert state_hash(restored.world) == expected
    assert restored.world.agents[a.id].memory == a.memory
    restored.reset(WorldConfig(infinite=True))
    assert restored.world.agents[a.id].memory is None
    assert store.replay(run_id).agents[a.id].memory == a.memory
    store.close()


def test_dialogue_is_retained_by_both_participants():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    a, b = list(engine.world.agents.values())[:2]
    a.position, b.position = Position(x=0, y=0), Position(x=1, y=0)
    intent = AgentIntent(
        actor_id=a.id,
        action=Action.SOCIALIZE,
        peer_id=b.id,
        utterance="Hello",
        decision=Decision(selected_goal="socialize"),
    )
    experience(engine.world, a, intent, True, "socialized", 1, action_snapshot(a))
    for participant in (a, b):
        assert any(m.kind == "dialogue" for m in participant.memory.long_term)
    store.close()
