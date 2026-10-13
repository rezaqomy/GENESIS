from fastapi.testclient import TestClient

from app.main import create_app
from app.simulation.events.reducer import state_hash


def test_infinite_stream_camera_reads_reset_and_replay(monkeypatch):
    monkeypatch.setenv("GENESIS_INFINITE", "1")
    with TestClient(create_app(":memory:")) as client:
        initial = client.get("/api/world").json()
        assert initial["state"]["config"]["infinite"]
        assert initial["state"]["tiles"] == []
        assert len(client.get("/api/settlements").json()) == 1
        with client.websocket_connect("/ws/simulation") as ws:
            assert ws.receive_json()["type"] == "snapshot"
            ws.send_json({"type": "viewport", "chunks": [[-2, -1], [0, 0]]})
            chunks = ws.receive_json()
            assert chunks["type"] == "chunks"
            assert [c["key"] for c in chunks["chunks"]] == ["-2,-1", "0,0"]
            assert all(len(c["terrain"]) == 1024 for c in chunks["chunks"])
            assert client.get("/api/world").json()["state_hash"] == initial["state_hash"]
            assert client.get("/api/chunks/-2/-1").status_code == 200
            before = state_hash(client.app.state.simulation.engine.world)
            for cx in range(-8, 8):
                client.get(f"/api/chunks/{cx}/4")
            assert state_hash(client.app.state.simulation.engine.world) == before
            result = client.post("/api/simulation/step").json()
            entity = ws.receive_json()
            assert entity["type"] == "entities" and "chunks" not in entity
            assert entity["sequence_number"] == result["sequence_number"]
            assert entity["state"]["tiles"] == []
            assert all(
                "intent" not in e["payload"] and "state" not in e["payload"]
                for e in entity["events"]
            )
            assert all(
                e["tick"] == 1 or e["event_type"] == "COMMAND_ACCEPTED" for e in entity["events"]
            )
            assert entity["metrics"]["active_chunks"] <= 36
            ws.send_text("resync")
            assert ws.receive_json()["state_hash"] == result["state_hash"]
        replay = client.get(f"/api/replay/{initial['run_id']}").json()
        assert replay["state_hash"] == result["state_hash"]
        reset = client.post("/api/simulation/reset", json={"seed": 13}).json()
        assert reset["state"]["config"]["infinite"]
        assert (
            reset["state"]["config"]["utility_weights"]
            == initial["state"]["config"]["utility_weights"]
        )
        assert reset["run_id"] != initial["run_id"]


def test_optional_memory_fields_survive_older_snapshot_restart():
    from app.simulation.engine.core import Engine
    from app.simulation.engine.generation import generate_world
    from app.simulation.events.reducer import WorldEvent, authoritative_state
    from app.simulation.models.domain import WorldConfig, WorldState
    from app.simulation.persistence.sqlite import EventStore
    from app.simulation.policies.utility import UtilityPolicy

    raw = authoritative_state(generate_world(WorldConfig(infinite=True)))
    for a in raw["agents"].values():
        a["food_memory"] = {}  # Early recordings explicitly stored an empty food memory.
        a.pop("known_resources", None)
        a.pop("recent_positions", None)
    old_world = WorldState.model_validate(raw)
    store = EventStore(":memory:")
    store.append(
        [
            WorldEvent(
                run_id="older-phase2",
                sequence_number=1,
                tick=0,
                event_type="WORLD_CREATED",
                payload={"state": raw},
            )
        ],
        old_world,
    )
    engine = Engine(WorldConfig(infinite=True), store, UtilityPolicy(), restore=True)
    assert state_hash(engine.world) == state_hash(old_world)
    for _ in range(25):
        engine.tick()
    assert state_hash(engine.world) == state_hash(store.replay(engine.run_id))
    assert state_hash(engine.world) == state_hash(store.replay(engine.run_id, use_snapshot=True))
    store.close()
