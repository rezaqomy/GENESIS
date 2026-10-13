import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.simulation import SimulationService
from app.simulation.models.domain import WorldConfig


def test_api_validation_and_websocket():
    with TestClient(create_app(":memory:")) as client:
        assert client.get("/health").json() == {"status": "ok"}
        initial = client.get("/api/world").json()
        assert len(client.get("/api/agents").json()) == 10
        assert client.get("/api/agents/unknown").status_code == 404
        assert client.post("/api/simulation/speed", json={"multiplier": 3}).status_code == 422
        assert client.post("/api/simulation/reset", json={"seed": -1}).status_code == 422
        assert client.get("/api/events?after=-1").status_code == 422
        with client.websocket_connect("/ws/simulation") as ws:
            assert ws.receive_json()["state"]["tick"] == 0
            response = client.post("/api/simulation/step").json()
            update = ws.receive_json()
            assert update["state"]["tick"] == 1
            assert update["sequence_number"] == response["sequence_number"]
            ws.send_text("resync")
            assert ws.receive_json()["state_hash"] == response["state_hash"]
        replay = client.get(f"/api/replay/{initial['run_id']}").json()
        assert replay["state_hash"] == response["state_hash"]
        assert client.post("/api/simulation/start").status_code == 200
        assert client.post("/api/simulation/step").status_code == 409
        assert client.post("/api/simulation/pause").status_code == 200
        reset = client.post("/api/simulation/reset", json={"seed": 7}).json()
        assert reset["run_id"] != initial["run_id"]
        assert reset["state"]["tick"] == 0
        assert reset["state"]["config"]["seed"] == 7
        assert client.get(f"/api/replay/{initial['run_id']}").status_code == 200


@pytest.mark.asyncio
async def test_single_writer_pause_and_fifo():
    svc = SimulationService(":memory:", WorldConfig())
    svc.start()
    await asyncio.gather(*(svc.submit("step") for _ in range(3)))
    assert svc.engine.world.tick == 3
    await asyncio.sleep(0.55)
    assert svc.engine.world.tick == 3
    await svc.submit("speed", 8)
    await svc.submit("start")
    for _ in range(30):
        if svc.engine.world.tick > 3:
            break
        await asyncio.sleep(0.02)
    await svc.submit("pause")
    tick = svc.engine.world.tick
    assert tick > 3
    await asyncio.sleep(0.1)
    assert svc.engine.world.tick == tick
    await svc.close()


@pytest.mark.asyncio
async def test_database_ownership_and_restart(tmp_path):
    path = str(tmp_path / "world.sqlite")
    svc = SimulationService(path, WorldConfig(seed=19))
    svc.start()
    with pytest.raises(RuntimeError, match="already running"):
        svc.start()
    with pytest.raises(RuntimeError, match="already owns"):
        SimulationService(path, WorldConfig())
    await svc.submit("step")
    await svc.submit("start")
    run_id = svc.engine.run_id
    await svc.close()
    restored = SimulationService(path, WorldConfig(seed=99))
    try:
        assert restored.engine.run_id == run_id
        assert restored.engine.world.config.seed == 19
        assert restored.engine.world.tick == 1
        assert restored.engine.world.status == "paused"
        assert restored.store.replay(run_id) == restored.engine.world
    finally:
        await restored.close()
