"""Bounded isolated real-engine population benchmark; never changes the live world.

Run from repo root with .venv/bin/python scripts/benchmark_capacity.py.
Laya requests use the existing shared server, so background load is part of results.
"""

import argparse
import asyncio
import json
import math
import resource
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.simulation.cognition.runtime import CognitionPolicy, Settings  # noqa: E402
from app.simulation.chunks.access import WorldAccess  # noqa: E402
from app.simulation.engine.core import Engine  # noqa: E402
from app.simulation.events.reducer import authoritative_state  # noqa: E402
from app.simulation.models.domain import WorldConfig, WorldState  # noqa: E402
from app.simulation.policies.utility import UtilityPolicy  # noqa: E402
from app.simulation.persistence.sqlite import EventStore  # noqa: E402


def percentiles(values):
    ordered = sorted(values)
    return {
        f"p{p}": round(ordered[max(0, math.ceil(len(ordered) * p / 100) - 1)], 2)
        for p in (50, 95, 100)
    }


async def evaluate(count, cognitive, ticks, checkpoint=None):
    with tempfile.TemporaryDirectory(prefix="genesis-capacity-") as directory:
        db = Path(directory) / "world.sqlite"
        store = EventStore(str(db))
        policy = UtilityPolicy()
        if cognitive:
            # Match the documented live CPU Laya settings; disable unrelated dialogue.
            policy = CognitionPolicy(policy, Settings())
        engine = Engine(
            WorldConfig(infinite=True, seed=42, agent_count=count), store, policy
        )
        if checkpoint:
            engine.world = WorldState.model_validate(checkpoint)
            engine.access = WorldAccess(engine.world)
            store.append(
                [
                    engine.event(
                        "WORLD_CREATED", {"state": authoritative_state(engine.world)}
                    )
                ],
                engine.world,
            )
        assert len(engine.world.agents) == count
        initial_tick = engine.world.tick
        if cognitive:
            policy.reset(engine.run_id)
        durations, decisions, serializations, ages = [], [], [], []
        before_cpu = time.process_time()
        started = time.perf_counter()
        for index in range(ticks):
            tick_start = time.perf_counter()
            engine.tick()
            duration = (time.perf_counter() - tick_start) * 1000
            serialization_start = time.perf_counter()
            payload = json.dumps(authoritative_state(engine.world))
            serialization = (time.perf_counter() - serialization_start) * 1000
            if index >= 10:
                durations.append(duration)
                decisions.append(engine.metrics["decision_duration_ms"])
                serializations.append(serialization)
                if cognitive:
                    ages.extend(
                        engine.world.tick - item[1] for item in policy.results.values()
                    )
            # Keep the event loop responsive; cap cognitive runs at live 1x cadence.
            await asyncio.sleep(
                max(0.001, 0.5 - (time.perf_counter() - tick_start)) if cognitive else 0
            )
        elapsed = time.perf_counter() - started
        result = {
            "agents_requested": count,
            "agents_actual": len(engine.world.agents),
            "alive_final": sum(a.alive for a in engine.world.agents.values()),
            "mode": "laya_shared_server_1x" if cognitive else "utility_unpaced",
            "ticks": ticks,
            "initial_tick": initial_tick,
            "scenario": "checkpoint" if checkpoint else "fresh_world",
            "warmup_ticks_excluded": 10,
            "wall_seconds": round(elapsed, 2),
            "process_cpu_seconds": round(time.process_time() - before_cpu, 2),
            "tick_ms": percentiles(durations),
            "decision_ms": percentiles(decisions),
            "state_serialization_ms": percentiles(serializations),
            "final_state_bytes": len(payload.encode()),
            "database_bytes": sum(
                p.stat().st_size for p in Path(directory).glob("world.sqlite*")
            ),
            "process_peak_rss_mib_cumulative": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
            ),
        }
        if cognitive:
            result["cognition"] = policy.status()
            result["cached_observation_age_ticks"] = percentiles(ages) if ages else None
            result["laya_applied_fraction"] = round(
                policy.stats["consumed"] / max(1, policy.stats["decisions"]), 3
            )
            tasks = list(policy.tasks.values()) + list(policy.dialogue_tasks.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await policy.client.aclose()
        store.close()
        return result


async def main(args):
    results = []
    checkpoint = json.loads(args.checkpoint.read_text()) if args.checkpoint else None
    if checkpoint and "state" in checkpoint:
        checkpoint = checkpoint["state"]
    counts = [len(checkpoint["agents"])] if checkpoint else args.counts
    for mode in args.modes:
        for count in counts:
            row = await evaluate(count, mode == "laya", args.ticks, checkpoint)
            results.append(row)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(results, indent=2) + "\n")
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", type=int, nargs="+", default=[10, 20, 30])
    parser.add_argument("--ticks", type=int, default=100)
    parser.add_argument(
        "--modes", choices=["utility", "laya"], nargs="+", default=["utility", "laya"]
    )
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/evaluations/capacity.json")
    )
    args = parser.parse_args()
    if args.ticks <= 10:
        parser.error("ticks must exceed the 10-tick warmup")
    asyncio.run(main(args))
