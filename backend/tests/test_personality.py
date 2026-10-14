from app.simulation.engine.core import Engine
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import Action, Position, WorldConfig
from app.simulation.observation.builder import build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.personality import personality_for
from app.simulation.policies.utility import UtilityPolicy


def test_personality_reproducible_distinct_and_normalized():
    traits = [personality_for(42, i) for i in range(10)]
    assert traits == [personality_for(42, i) for i in range(10)]
    assert len({t.model_dump_json() for t in traits}) == 10
    assert traits != [personality_for(43, i) for i in range(10)]
    assert all(0 <= v <= 1 for t in traits for v in t.model_dump().values())


def test_utility_survival_commitment_and_explanations():
    s = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), s, UtilityPolicy())
    a = next(iter(e.world.agents.values()))
    a.hunger = 95
    a.inventory.food = 1
    a.energy = 1
    intent = e.policy.decide(build_observation(e.world, a.id, access=e.access))
    assert intent.action == Action.EAT
    assert intent.decision.selected_goal == "eat"
    assert len(intent.decision.candidates) >= 13
    assert all(0 <= c.utility <= 1 for c in intent.decision.candidates)
    assert any(c.rejection for c in intent.decision.candidates)
    e.tick([intent])
    assert a.decision.factors and a.decision.commitment_until > 0
    assert e.store.replay(e.run_id).agents[a.id].decision == a.decision
    s.close()


def test_return_home_and_personality_exploration():
    s = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), s, UtilityPolicy())
    a = next(iter(e.world.agents.values()))
    a.position = Position(x=45, y=-4)
    from app.simulation.models.domain import Terrain, Tile

    for y in range(-12, 5):
        for x in range(37, 54):
            e.world.terrain_modifications[f"{x},{y}"] = Tile(
                position=Position(x=x, y=y), terrain=Terrain.GRASS, walkable=True
            )
    a.home = Position(x=0, y=0)
    a.hunger = 10
    a.inventory.food = 3
    a.energy = 60
    a.psychology.homesickness = 1
    a.psychology.fear = 0.8
    a.personality.loyalty = 1
    a.personality.exploration_drive = 0
    a.personality.curiosity = 0
    intent = e.policy.decide(build_observation(e.world, a.id, access=e.access))
    assert intent.decision.selected_goal in ("return_home", "seek_safety")
    assert intent.action == Action.MOVE
    a.position = Position(x=0, y=0)
    a.energy = 100
    a.hunger = 0
    a.psychology.fear = 0
    a.psychology.homesickness = 0
    a.personality.curiosity = 1
    a.personality.independence = 1
    a.personality.exploration_drive = 1
    a.personality.loyalty = 0
    a.personality.sociability = 0
    a.personality.risk_tolerance = 1
    intent = e.policy.decide(build_observation(e.world, a.id, access=e.access))
    assert intent.decision.selected_goal == "explore"
    assert a.position.distance(intent.destination) > 16
    s.close()


def test_psychology_social_proximity_and_camera_independence():
    stores = [EventStore(":memory:") for _ in range(2)]
    engines = [Engine(WorldConfig(infinite=True), s, UtilityPolicy()) for s in stores]
    for e in engines:
        for _ in range(40):
            e.tick()
        assert all(a.psychology.loneliness <= 0.2 for a in e.world.agents.values())
        assert all(a.known_chunks for a in e.world.agents.values())
        assert state_hash(e.world) == state_hash(e.store.replay(e.run_id))
    assert state_hash(engines[0].world) == state_hash(engines[1].world)
    for s in stores:
        s.close()


def test_food_memory_kind_and_configurable_weights():
    from app.simulation.models.domain import UtilityWeights
    from app.simulation.settlements.environment import experience_tick

    s = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), s, UtilityPolicy())
    a = e.world.agents["agent-00"]
    experience_tick(e.world, e.access)
    assert a.food_memory and all(k.endswith(":food") for k in a.food_memory)
    assert len(a.food_memory) <= 16
    observation = build_observation(e.world, a.id, access=e.access)
    standard = e.policy.decide(observation).decision
    cautious = (
        UtilityPolicy(UtilityWeights(trait=0, scarcity=0).model_dump()).decide(observation).decision
    )
    assert standard.candidates != cautious.candidates
    explore = next(c for c in cautious.candidates if c.goal == "explore")
    assert explore.factors["curiosity"] == 0
    assert e.world.config.utility_weights.need == 0.55
    s.close()


def test_model_goal_respects_commitment_but_can_recover_and_handle_emergency():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    try:
        a = engine.world.agents["agent-00"]
        a.energy, a.hunger, a.inventory.food = 60, 20, 1
        observation = build_observation(engine.world, a.id, access=engine.access)
        resting = engine.policy.decide(observation, preferred_goal="rest")
        assert resting.decision.selected_goal == "rest"
        a.decision = resting.decision
        observation = build_observation(engine.world, a.id, access=engine.access)
        assert engine.policy.decide(observation, preferred_goal="find_food").action == Action.REST
        # A new model goal becomes eligible once commitment expires.
        observation.tick = a.decision.commitment_until
        assert (
            engine.policy.decide(observation, preferred_goal="find_food").decision.selected_goal
            == "find_food"
        )
        # Repeated failures allow replanning before the commitment deadline.
        observation.tick = 0
        observation.self_agent.decision.failures = 3
        assert (
            engine.policy.decide(observation, preferred_goal="find_food").decision.selected_goal
            == "find_food"
        )
        # Hunger emergencies still interrupt any commitment.
        observation.self_agent.hunger = 95
        assert engine.policy.decide(observation, preferred_goal="explore").action == Action.EAT
    finally:
        store.close()
