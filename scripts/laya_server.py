"""CPU-only local Laya decision service, isolated from the simulation's dependencies."""

import asyncio
from collections import defaultdict
import os
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

MODEL = os.getenv("GENESIS_LAYA_MODEL", "convaiinnovations/laya-multilingual")
REVISION = os.getenv(
    "GENESIS_LAYA_REVISION", "1720e3e3357cfe1e281542e223f8273b0890ca34"
)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(max_length=10000)
    criteria: dict[str, str] = Field(min_length=1, max_length=16)


@asynccontextmanager
async def lifespan(app):
    import laya
    import torch

    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    app.state.lock = asyncio.Lock()
    app.state.agent = await asyncio.to_thread(
        laya.load, MODEL, device="cpu", revision=REVISION
    )
    yield
    del app.state.agent


app = FastAPI(title="Genesis local Laya", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL, "revision": REVISION, "device": "cpu"}


@app.post("/decide")
async def decide(body: Request):
    questions = {
        "goal": {
            "type": "choice",
            "instructions": "Choose this villager's next goal using needs, personality, memories and environment.",
            "criteria": body.criteria,
        }
    }
    async with app.state.lock:
        started = perf_counter()
        try:
            result = await asyncio.to_thread(
                app.state.agent.predict,
                body.state,
                questions,
                max_len=1024,
                head_max_len=384,
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(
                status_code=503, detail="Laya inference failed"
            ) from exc
        answer = result["answers"]["goal"]
        return {
            "goal": answer["choice"],
            "probability": answer["answer_confidence"],
            "probabilities": answer.get("probabilities", {}),
            "model": MODEL,
            "revision": REVISION,
            "device": "cpu",
            "inference_ms": round((perf_counter() - started) * 1000, 2),
        }


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requests: list[Request] = Field(min_length=1, max_length=30)


def batch_predict(agent, requests):
    # Identical legal choice sets can share a forward pass; differing sets stay separate.
    groups = defaultdict(list)
    for index, body in enumerate(requests):
        groups[tuple(sorted(body.criteria.items()))].append((index, body))
    results = [None] * len(requests)
    for criteria, rows in groups.items():
        questions = {
            "goal": {
                "type": "choice",
                "instructions": "Choose the villager's next goal using needs, personality, memories and environment.",
                "criteria": dict(criteria),
            }
        }
        started = perf_counter()
        predictions = agent.predict_batch(
            [body.state for _, body in rows],
            questions,
            batch_size=4,
            max_len=1024,
            head_max_len=384,
        )
        elapsed = (perf_counter() - started) * 1000
        for (index, _), prediction in zip(rows, predictions, strict=True):
            answer = prediction["answers"]["goal"]
            results[index] = {
                "goal": answer["choice"],
                "probability": answer["answer_confidence"],
                "probabilities": answer.get("probabilities", {}),
                "model": MODEL,
                "revision": REVISION,
                "device": "cpu",
                "inference_ms": round(elapsed / len(rows), 2),
            }
    return results


@app.post("/decide-batch")
async def decide_batch(body: BatchRequest):
    async with app.state.lock:
        try:
            results = await asyncio.to_thread(
                batch_predict, app.state.agent, body.requests
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(
                status_code=503, detail="Laya batch inference failed"
            ) from exc
    return {"results": results}
