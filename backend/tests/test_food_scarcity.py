"""Depleted food stays depleted and hunger drives local foraging travel."""

import pytest

from app.simulation.chunks.access import WorldAccess
from app.simulation.engine.core import Engine
from app.simulation.engine.generation import generate_world
from app.simulation.events.reducer import authoritative_state, state_hash
from app.simulation.models.domain import Action, Position, Terrain, Tile, WorldConfig
from app.simulation.observation.builder import Observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


def test_berries_need_elapsed_days_and_repeated_picking_delays_recovery():
    world = generate_world(WorldConfig(infinite=True))
    access = WorldAccess(world)
    rid = "r:4:-4:food"
    world.tick = 479
    access.harvest(access.resource(rid), 8)
    world.tick = 480
    assert access.resource(rid).quantity == 0
    world.tick = 958
    assert access.resource(rid).quantity == 0
    world.tick = 959
    assert access.resource(rid).quantity == 1
    access.harvest(access.resource(rid))
    world.tick = 960
    assert access.resource(rid).quantity == 0
    # Camera reads and chunk eviction cannot grow fruit.
    for x in range(80):
        access.projection(x, 20)
    assert access.resource(rid).quantity == 0
    world.tick = 1439
    assert access.resource(rid).quantity == 1


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("tick", [19, 498])
def test_engine_keeps_depletion_until_real_recovery_and_replays(enabled, tick):
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True, regeneration_ticks=20 if enabled else 0), store)
    world = engine.world
    world.tick = 19
    rid = "r:4:-4:food"
    engine.access.harvest(engine.access.resource(rid), 1)
    world.tick = tick
    # Record the aged, harvested fixture as a replayable initial state.
    store.append([engine.event("WORLD_CREATED", {"state": authoritative_state(world)})], world)
    events = engine.tick([])
    recovered = enabled and tick == 498
    assert engine.access.resource(rid).quantity == (8 if recovered else 7)
    assert (rid not in world.resource_modifications) == recovered
    assert any(e.event_type == "RESOURCE_RESTORED" for e in events) == recovered
    assert state_hash(world) == state_hash(store.replay(engine.run_id))
    assert state_hash(world) == state_hash(store.replay(engine.run_id, use_snapshot=True))
    store.close()


def barren_observation(hunger=95, energy=80):
    world = generate_world(WorldConfig(infinite=True))
    a = world.agents["agent-00"]
    a.position = Position(x=0, y=0)
    a.inventory.food = 0
    a.hunger, a.energy = hunger, energy
    tiles = [
        Tile(position=Position(x=x, y=y), terrain=Terrain.GRASS, walkable=True)
        for x in range(-8, 9)
        for y in range(-8, 9)
        if abs(x) + abs(y) <= 8
    ]
    return Observation(seed=42, tick=10, self_agent=a, tiles=tiles, resources=[], occupied=[])


def test_hungry_agent_searches_unseen_ground_without_global_food_information():
    o = barren_observation()
    origin = o.self_agent.position.model_copy()
    visited = []
    for tick in range(10, 22):
        o.tick = tick
        intent = UtilityPolicy().decide(o)
        assert intent.action == Action.MOVE
        assert intent.decision.selected_goal == "find_food"
        assert intent.target in [t.position for t in o.tiles]
        assert o.self_agent.position.distance(intent.target) == 1
        visited.append(o.self_agent.position.model_copy())
        o.self_agent.position = intent.target
        o.self_agent.decision = intent.decision
        o.self_agent.recent_positions = visited[-16:]
        # Slide the perception window, without revealing any remote food.
        o.tiles = [
            t.model_copy(
                update={
                    "position": Position(
                        x=t.position.x + intent.target.x - visited[-1].x,
                        y=t.position.y + intent.target.y - visited[-1].y,
                    )
                }
            )
            for t in o.tiles
        ]
    assert origin.distance(o.self_agent.position) >= 6


def test_exhausted_hungry_forager_recovers_before_searching():
    intent = UtilityPolicy().decide(barren_observation(energy=5))
    assert intent.action == Action.REST


def test_food_search_works_with_minimum_vision_and_ignores_empty_food_memory():
    from app.simulation.models.domain import Resource

    o = barren_observation()
    o.vision_radius = 1
    o.self_agent.food_memory = {"r:1:0:food": 8}
    o.tiles = [t for t in o.tiles if t.position.distance(o.self_agent.position) <= 1]
    o.resources = [
        Resource(id="r:1:0:food", position=Position(x=1, y=0), kind="food", quantity=0, capacity=8)
    ]
    intent = UtilityPolicy().decide(o)
    assert intent.action == Action.MOVE
    assert intent.decision.selected_goal == "find_food"
    assert intent.target.distance(o.self_agent.position) == 1


def test_food_search_avoids_unreachable_frontiers():
    o = barren_observation()
    # All distant cells remain visible but a barrier isolates this short corridor.
    reachable = {(0, 0), (1, 0), (2, 0)}
    for tile in o.tiles:
        tile.walkable = (tile.position.x, tile.position.y) in reachable or tile.position.x < -2
    intent = UtilityPolicy().decide(o)
    assert intent.action == Action.MOVE
    assert intent.target == Position(x=1, y=0)
    assert intent.destination == Position(x=2, y=0)


def test_repeated_food_route_loop_temporarily_yields_to_fresh_search():
    o = barren_observation()
    a = o.self_agent
    a.food_memory = {"r:9:0:food": 8}
    a.decision.selected_goal = "find_food"
    a.decision.target = Position(x=9, y=0)
    a.recent_positions = [Position(x=0, y=0), Position(x=0, y=1)] * 4
    intent = UtilityPolicy().decide(o)
    assert intent.action == Action.MOVE
    assert intent.decision.selected_goal == "find_food"
    assert intent.destination != Position(x=9, y=0)
    assert intent.decision.cooldowns["remembered_food"] > o.tick
    a.position = intent.target
    a.decision = intent.decision
    a.recent_positions = []  # The escape remains active after the immediate loop ends.
    next_intent = UtilityPolicy().decide(o)
    assert next_intent.destination != Position(x=9, y=0)
