import json

from app.simulation.actions.resolver import resolve_intent
from app.simulation.chunks.access import ChunkCache, WorldAccess
from app.simulation.chunks.generator import chunk_coord, generate_chunk, terrain_at
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import authoritative_state, state_hash
from app.simulation.models.domain import Action, AgentIntent, Position, WorldConfig
from app.simulation.pathfinding.astar import astar, region_route
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.rules import RulePolicy


def test_chunk_order_negative_coordinates_and_seams():
    a, b = ChunkCache(42, 2, 16), ChunkCache(42, 2, 16)
    positions = [(0, 0), (-1, -1), (1, 0), (-2, 3)]
    first = {p: a.get(*p).model_dump() for p in positions}
    second = {p: b.get(*p).model_dump() for p in reversed(positions)}
    assert first == second
    assert chunk_coord(Position(x=-1, y=-33)) == (-1, -2)
    c = generate_chunk(42, -1, 0)
    assert c.tiles[31].position == Position(x=-1, y=0)
    assert all(t.terrain == terrain_at(42, t.position.x, t.position.y) for t in c.tiles)


def test_unload_reload_and_lazy_regeneration():
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), store)
    r = e.access.resource("r:4:-4:food")
    e.access.harvest(r, 3)
    assert e.access.resource(r.id).quantity == 5
    for i in range(80):
        e.access.cache.get(i, 10)
    assert len(e.access.cache.entries) <= e.world.config.chunk_cache_size
    assert e.access.resource(r.id).quantity == 5
    e.world.tick = 60
    assert e.access.resource(r.id).quantity == 5
    e.world.tick = 1440
    assert e.access.resource(r.id).quantity == 8
    store.close()


def test_cross_chunk_and_astar_budget():
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), store)
    a = next(iter(e.world.agents.values()))
    a.position = Position(x=31, y=0)
    # Choose a walkable boundary, rather than relying on biome placement for seed 42.
    from app.simulation.models.domain import Terrain, Tile

    e.world.terrain_modifications["32,0"] = Tile(
        position=Position(x=32, y=0), terrain=Terrain.GRASS, walkable=True
    )
    assert resolve_intent(
        e.world,
        AgentIntent(actor_id=a.id, action=Action.MOVE, target=Position(x=32, y=0)),
        e.access,
    )[0]
    assert chunk_coord(a.position) == (1, 0)
    start = Position(x=-1, y=0)
    walkable = {(x, 0) for x in range(-1, 40)}
    assert len(astar(start, {(33, 0)}, walkable)) == 34
    assert astar(start, {(33, 0)}, walkable, budget=2) is None
    assert region_route(start, Position(x=65, y=-1)) == ["0,0", "1,0", "2,0", "2,-1"]
    store.close()


def test_camera_reads_do_not_change_authority_or_persist_tiles():
    stores = [EventStore(":memory:") for _ in range(2)]
    engines = [Engine(WorldConfig(infinite=True), s, RulePolicy()) for s in stores]
    for tick in range(25):
        visual = WorldAccess(engines[1].world, ChunkCache(42, 2, 16))
        visual.projection(tick - 12, 9)
        for e in engines:
            e.tick()
    assert state_hash(engines[0].world) == state_hash(engines[1].world)
    for e in engines:
        assert state_hash(e.world) == state_hash(e.store.replay(e.run_id))
        assert state_hash(e.world) == state_hash(e.store.replay(e.run_id, use_snapshot=True))
        initial = e.store.events(e.run_id)[0].payload["state"]
        assert initial["tiles"] == [] and initial["resources"] == {}
        assert len(json.dumps(authoritative_state(e.world))) < 100000
        e.store.close()
