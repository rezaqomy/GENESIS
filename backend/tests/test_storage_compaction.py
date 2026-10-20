import sqlite3

import pytest

from app.simulation.engine.core import Engine
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import WorldConfig
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.rules import RulePolicy


def test_payload_compression_preserves_unicode_and_message():
    payload = {"state": "حافظه" * 30000, "message": "سلام"}
    encoded = EventStore.encode_payload(payload)
    assert len(encoded) < 2000
    assert EventStore.decode_payload(encoded) == payload
    assert EventStore.decode_payload('{"old":true}') == {"old": True}


def test_compaction_keeps_state_and_can_continue_after_restore(tmp_path):
    path = str(tmp_path / "world.sqlite")
    store = EventStore(path)
    engine = Engine(WorldConfig(), store, RulePolicy())
    for _ in range(55):
        engine.tick([])
    run = engine.run_id
    digest = state_hash(engine.world)
    old_count = store.connection.execute("SELECT count(*) FROM events").fetchone()[0]
    with store.transaction():
        store.compact(run, 25)
    assert state_hash(store.replay(run)) == digest
    assert state_hash(store.replay(run, use_snapshot=True)) == digest
    history = store.history(run)
    assert history["compacted_through"][1] == 25
    assert sum(row[2] for row in history["counts"]) > 0
    assert store.connection.execute("SELECT count(*) FROM events").fetchone()[0] < old_count
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute("DELETE FROM events")
    store.close()
    store = EventStore(path)
    restored = Engine(WorldConfig(), store, RulePolicy(), restore=True)
    restored.tick([])
    assert state_hash(store.replay(run)) == state_hash(restored.world)
    store.close()


def test_compaction_rolls_back_atomically():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(), store, RulePolicy())
    for _ in range(26):
        engine.tick([])
    count = store.connection.execute("SELECT count(*) FROM events").fetchone()[0]
    with pytest.raises(RuntimeError), store.transaction():
        store.compact(engine.run_id, 25)
        raise RuntimeError("abort")
    assert store.connection.execute("SELECT count(*) FROM events").fetchone()[0] == count
    assert store.history(engine.run_id)["compacted_through"] is None
    assert state_hash(store.replay(engine.run_id)) == state_hash(engine.world)
    store.close()


def test_automatic_compaction_at_snapshot_boundary():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(), store, RulePolicy())
    for _ in range(26):
        engine.tick([])
    engine.world.tick = 999
    engine.tick([])
    assert store.history(engine.run_id)["compacted_through"][1] == 25
    assert state_hash(store.replay(engine.run_id)) == state_hash(engine.world)
    store.close()
