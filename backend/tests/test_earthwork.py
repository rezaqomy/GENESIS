import json

import pytest

from app.simulation.actions.resolver import resolve_intent
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import authoritative_state, state_hash
from app.simulation.models.domain import Action, AgentIntent, Position, Terrain, Tile, WorldConfig
from app.simulation.observation.builder import build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


@pytest.fixture
def setup():
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    a = next(iter(e.world.agents.values()))
    a.position = Position(x=100, y=100)
    # Find an adjacent site with no natural resource node.
    for x in range(101, 150):
        target = Position(x=x, y=100)
        if not e.access.visible_resources(target, 0):
            a.position = Position(x=x - 1, y=100)
            break
    e.world.terrain_modifications[f"{target.x},{target.y}"] = Tile(
        position=target, terrain=Terrain.ROCK, walkable=False
    )
    a.inventory.tools["pickaxe"] = 2
    a.inventory.stone = 0
    yield e, a, target
    store.close()


def test_mining_changes_collision_and_conserves_material_through_placement(setup):
    e, a, target = setup
    mine = AgentIntent(actor_id=a.id, action=Action.MINE, target=target)
    assert resolve_intent(e.world, mine, e.access)[0]
    assert e.access.tile(target).walkable
    assert a.inventory.stone == 1 and a.inventory.tools["pickaxe"] == 1
    assert not resolve_intent(e.world, mine, e.access)[0]
    place = AgentIntent(actor_id=a.id, action=Action.PLACE_BLOCK, target=target, item="stone")
    assert resolve_intent(e.world, place, e.access)[0]
    assert not e.access.tile(target).walkable and a.inventory.stone == 0
    assert resolve_intent(e.world, mine, e.access)[0]
    assert a.inventory.stone == 1 and a.inventory.tools["pickaxe"] == 0
    assert resolve_intent(e.world, place, e.access)[0]
    assert not resolve_intent(e.world, mine, e.access)[0]
    assert a.inventory.stone == 0


def test_range_occupancy_water_and_energy_are_authoritative(setup):
    e, a, target = setup
    mine = AgentIntent(actor_id=a.id, action=Action.MINE, target=target)
    a.energy = 5
    assert not resolve_intent(e.world, mine, e.access)[0]
    a.energy = 90
    peer = list(e.world.agents.values())[1]
    peer.position = target.model_copy()
    assert not resolve_intent(e.world, mine, e.access)[0]
    peer.position = Position(x=0, y=0)
    a.position = Position(x=0, y=0)
    assert not resolve_intent(e.world, mine, e.access)[0]
    a.position = Position(x=target.x - 1, y=target.y)
    e.world.terrain_modifications[f"{target.x},{target.y}"].terrain = Terrain.WATER
    a.inventory.stone = 1
    assert not resolve_intent(e.world, mine, e.access)[0]
    assert not resolve_intent(
        e.world,
        AgentIntent(actor_id=a.id, action=Action.PLACE_BLOCK, target=target, item="stone"),
        e.access,
    )[0]
    assert a.inventory.stone == 1


def test_earth_is_finite_and_can_prepare_a_fertile_tile(setup):
    e, a, target = setup
    e.world.terrain_modifications[f"{target.x},{target.y}"] = Tile(
        position=target, terrain=Terrain.SOIL, walkable=True
    )
    a.inventory.clay = 0
    dig = AgentIntent(actor_id=a.id, action=Action.DIG, target=target)
    assert resolve_intent(e.world, dig, e.access)[0]
    assert a.inventory.clay == 1
    assert not resolve_intent(e.world, dig, e.access)[0]
    assert resolve_intent(
        e.world,
        AgentIntent(actor_id=a.id, action=Action.PLACE_BLOCK, target=target, item="clay"),
        e.access,
    )[0]
    assert e.access.tile(target).terrain == Terrain.SOIL and a.inventory.clay == 0


def test_local_policy_and_terrain_events_replay(setup):
    e, a, target = setup
    a.hunger, a.energy, a.inventory.food = 10, 90, 2
    intent = e.policy.decide(
        build_observation(e.world, a.id, access=e.access), preferred_goal="mine_building_material"
    )
    assert intent.action == Action.MINE and intent.target == target
    # Snapshot our fixture's starting state; ticks must log the terrain after-image.
    e.store.connection.execute(
        "UPDATE snapshots SET state=?,state_hash=? WHERE run_id=?",
        (json.dumps(authoritative_state(e.world)), state_hash(e.world), e.run_id),
    )
    e.store.connection.commit()
    e.tick([intent])
    assert e.access.tile(target).walkable
    assert state_hash(e.store.replay(e.run_id)) == state_hash(e.world)
    a.position = Position(x=-100, y=-100)
    o = build_observation(e.world, a.id, access=e.access)
    assert target not in [t.position for t in o.tiles]
