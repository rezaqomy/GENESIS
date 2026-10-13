import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.schemas import (
    EventsResponse,
    HealthResponse,
    ReplayResponse,
    ResetRequest,
    Snapshot,
    SpeedRequest,
)
from app.services.simulation import SimulationService
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import Agent, WorldConfig


def create_app(database: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = SimulationService(
            database or os.getenv("GENESIS_DB", "data/genesis.sqlite"),
            WorldConfig(seed=int(os.getenv("GENESIS_SEED", "42"))),
        )
        app.state.simulation = service
        service.start()
        yield
        await service.close()

    app = FastAPI(title="Genesis", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("GENESIS_ORIGINS", "http://localhost:5173").split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def service():
        return app.state.simulation

    async def control(name, value=None):
        try:
            return await service().submit(name, value)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/health", response_model=HealthResponse)
    async def health():
        task = service().task
        if task is None or task.done():
            raise HTTPException(status_code=503, detail="Simulation writer stopped")
        return {"status": "ok"}

    @app.get("/api/world", response_model=Snapshot)
    async def world():
        return service().snapshot()

    @app.get("/api/agents", response_model=list[Agent])
    async def agents():
        return list(service().engine.world.agents.values())

    @app.get("/api/agents/{agent_id}", response_model=Agent)
    async def agent(agent_id: str):
        a = service().engine.world.agents.get(agent_id)
        if a is None:
            raise HTTPException(status_code=404, detail="Unknown agent")
        return a

    @app.get("/api/events", response_model=EventsResponse)
    async def events(
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=500, ge=1, le=2000),
        run_id: str | None = None,
    ):
        run_id = run_id or service().engine.run_id
        rows = service().store.events(run_id, after, limit)
        return {
            "run_id": run_id,
            "events": rows,
            "next_sequence": rows[-1].sequence_number if rows else after,
        }

    @app.get("/api/replay/{run_id}", response_model=ReplayResponse)
    async def replay(run_id: str):
        try:
            state = service().store.replay(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"run_id": run_id, "state": state, "state_hash": state_hash(state)}

    @app.post("/api/simulation/start", response_model=Snapshot)
    async def start():
        return await control("start")

    @app.post("/api/simulation/pause", response_model=Snapshot)
    async def pause():
        return await control("pause")

    @app.post("/api/simulation/resume", response_model=Snapshot)
    async def resume():
        return await control("resume")

    @app.post("/api/simulation/step", response_model=Snapshot)
    async def step():
        return await control("step")

    @app.post("/api/simulation/reset", response_model=Snapshot)
    async def reset(body: ResetRequest):
        return await control("reset", body.seed)

    @app.post("/api/simulation/speed", response_model=Snapshot)
    async def speed(body: SpeedRequest):
        return await control("speed", body.multiplier)

    @app.websocket("/ws/simulation")
    async def simulation_socket(websocket: WebSocket):
        await websocket.accept()
        queue = asyncio.Queue(maxsize=1)
        svc = service()
        svc.subscribers.add(queue)
        queue.put_nowait(svc.snapshot())

        async def sender():
            while True:
                await websocket.send_json(await queue.get())

        async def receiver():
            while True:
                # Any client message requests an authoritative resynchronization.
                await websocket.receive_text()
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(svc.snapshot())

        tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            svc.subscribers.discard(queue)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return app


app = create_app()
