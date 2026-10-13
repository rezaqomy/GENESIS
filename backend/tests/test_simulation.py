import sqlite3

import pytest

from app.simulation.actions.resolver import advance_physiology, resolve_intent
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import Action, AgentIntent, Position, WorldConfig
from app.simulation.observation.builder import build_observation
from app.simulation.pathfinding.bfs import find_path
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.rules import RulePolicy


@pytest.fixture
def engine():
    store = EventStore(":memory:")
    yield Engine(WorldConfig(), store, RulePolicy())
    store.close()


def test_movement_validation(engine):
    w = engine.world
    a, b = list(w.agents.values())[:2]
    for tile in w.tiles:
        tile.walkable = True
    a.position = Position(x=0, y=0)
    b.position = Position(x=1, y=0)

    def move(x, y):
        return resolve_intent(
            w, AgentIntent(actor_id=a.id, action=Action.MOVE, target=Position(x=x, y=y))
        )[0]

    assert not move(1, 0)  # occupied
    assert not move(-1, 0)  # bounds
    assert not move(2, 0)  # teleport
    w.tiles[w.config.width].walkable = False
    assert not move(0, 1)  # terrain
    w.tiles[w.config.width].walkable = True
    assert move(0, 1)
    assert a.position == Position(x=0, y=1)


def test_resource_depletion_capacity_and_regeneration(engine):
    w = engine.world
    a = next(iter(w.agents.values()))
    r = next(iter(w.resources.values()))
    a.position = r.position.model_copy()
    r.quantity = 1
    intent = AgentIntent(actor_id=a.id, action=Action.GATHER, resource_id=r.id)
    assert resolve_intent(w, intent)[0]
    assert r.quantity == 0
    assert not resolve_intent(w, intent)[0]
    r.quantity = 1
    a.inventory.wood = a.inventory.capacity
    assert not resolve_intent(w, intent)[0]
    w.config.regeneration_ticks = 1
    engine.tick([])
    assert r.quantity == 2


def test_hunger_idle_and_rest(engine):
    a = next(iter(engine.world.agents.values()))
    hunger, energy = a.hunger, a.energy
    engine.tick([])
    assert a.hunger == hunger + 1 and a.energy == energy - 1
    a.energy = 1
    engine.tick([AgentIntent(actor_id=a.id, action=Action.REST)])
    assert a.energy == 14


def test_pathfinding():
    start = Position(x=0, y=0)
    assert find_path(start, {(2, 0)}, {(0, 0), (1, 0), (2, 0)}) == [
        Position(x=1, y=0),
        Position(x=2, y=0),
    ]
    assert find_path(start, {(2, 0)}, {(0, 0), (2, 0)}) is None
    assert find_path(start, {(0, 0)}, {(0, 0)}) == []


def test_observation_isolated(engine):
    a = next(iter(engine.world.agents.values()))
    o = build_observation(engine.world, a.id, radius=2)
    assert all(a.position.distance(t.position) <= 2 for t in o.tiles)
    o.self_agent.hunger = 100
    assert a.hunger != 100


def test_conflicts_stable_order(engine):
    w = engine.world
    a, b = list(w.agents.values())[:2]
    a.position = Position(x=1, y=1)
    b.position = Position(x=3, y=1)
    w.tiles[1 * w.config.width + 2].walkable = True
    intents = [
        AgentIntent(actor_id=c.id, action=Action.MOVE, target=Position(x=2, y=1)) for c in (b, a)
    ]
    events = engine.tick(intents)
    assert a.position == Position(x=2, y=1) and b.position == Position(x=3, y=1)
    assert any(e.event_type == "ACTION_REJECTED" for e in events)
    r = next(iter(w.resources.values()))
    r.position = Position(x=2, y=1)
    r.quantity = 1
    a.energy = b.energy = 50
    engine.tick(
        [AgentIntent(actor_id=c.id, action=Action.GATHER, resource_id=r.id) for c in (b, a)]
    )
    assert a.inventory.total == 1 and b.inventory.total == 0


def test_pause_step(engine):
    assert engine.world.status == "paused"
    engine.command("step")
    assert engine.world.tick == 1 and engine.world.status == "paused"
    engine.command("resume")
    with pytest.raises(ValueError):
        engine.command("step")
    engine.command("pause")
    engine.command("step")
    assert engine.world.tick == 2


def test_replay_determinism_and_behaviors(tmp_path):
    stores = [EventStore(str(tmp_path / f"world-{i}.db")) for i in range(2)]
    engines = [Engine(WorldConfig(), s, RulePolicy()) for s in stores]
    actions = set()
    for e in engines:
        e.command("start")
        for _ in range(150):
            events = e.tick()
            actions.update(x.payload["action"] for x in events if x.event_type == "ACTION_RESOLVED")
        e.command("pause")
        assert state_hash(e.world) == state_hash(e.store.replay(e.run_id))
        assert state_hash(e.world) == state_hash(e.store.replay(e.run_id, use_snapshot=True))
    assert state_hash(engines[0].world) == state_hash(engines[1].world)
    assert {"MOVE", "GATHER", "EAT", "REST"} <= actions
    run_id = engines[0].run_id
    stores[0].close()
    reopened = EventStore(str(tmp_path / "world-0.db"))
    assert state_hash(reopened.replay(run_id)) == state_hash(engines[0].world)
    with pytest.raises(sqlite3.IntegrityError):
        reopened.connection.execute("DELETE FROM events")
    reopened.close()
    stores[1].close()


def test_death_persisted_and_dead_action_rejected(engine):
    a = next(iter(engine.world.agents.values()))
    a.hunger = 100
    a.health = 3
    events = engine.tick([AgentIntent(actor_id=a.id, action=Action.REST)])
    assert not a.alive
    assert any(e.event_type == "AGENT_DIED" and e.actor_id == a.id for e in events)
    assert state_hash(engine.store.replay(engine.run_id)) == state_hash(engine.world)
    hunger, energy = a.hunger, a.energy
    advance_physiology(engine.world)
    assert (a.hunger, a.energy) == (hunger, energy)
    assert not resolve_intent(engine.world, AgentIntent(actor_id=a.id, action=Action.EAT))[0]


def test_policy_priorities(engine):
    a = next(iter(engine.world.agents.values()))
    a.hunger = 95
    a.inventory.food = 1
    a.energy = 2
    assert engine.policy.decide(build_observation(engine.world, a.id)).action == Action.EAT
    a.inventory.food = 0
    assert engine.policy.decide(build_observation(engine.world, a.id)).action == Action.REST
    assert not resolve_intent(engine.world, AgentIntent(actor_id=a.id, action=Action.EAT))[0]


def test_reset_same_seed(engine):
    initial = state_hash(engine.world)
    old_run = engine.run_id
    engine.command("step")
    engine.reset(WorldConfig())
    assert engine.run_id != old_run
    assert state_hash(engine.world) == initial
    assert engine.store.replay(old_run).tick == 1
