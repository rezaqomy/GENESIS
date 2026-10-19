"""Seeded behavior probe; --backend-root can point at an exported baseline checkout."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "backend",
    )
    parser.add_argument("--ticks", type=int, default=240)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 123])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.ticks < 1:
        parser.error("--ticks must be positive")
    sys.path.insert(0, str(args.backend_root.resolve()))
    from app.simulation.engine.core import Engine
    from app.simulation.events.reducer import authoritative_state, state_hash
    from app.simulation.models.domain import WorldConfig
    from app.simulation.persistence.sqlite import EventStore
    from app.simulation.policies.utility import UtilityPolicy

    results = []
    for seed in args.seeds:
        store = EventStore(":memory:")
        try:
            engine = Engine(
                WorldConfig(infinite=True, seed=seed), store, UtilityPolicy()
            )
            actions, rejected = Counter(), Counter()
            outcomes, navigation = Counter(), Counter()
            successful_tasks = []
            hunger, alive_samples, elapsed = 0, 0, 0.0
            for _ in range(args.ticks):
                started = perf_counter()
                events = engine.tick()
                elapsed += perf_counter() - started
                for event in events:
                    if event.event_type == "ACTION_RESOLVED":
                        actions[event.payload["action"]] += 1
                    elif event.event_type == "ACTION_REJECTED":
                        rejected[event.payload["message"]] += 1
                    elif event.event_type == "TASK_COMPLETED":
                        outcome = event.payload["outcome"]
                        outcomes[f"{outcome['kind']}:{outcome['status']}"] += 1
                        if outcome["status"] == "succeeded":
                            successful_tasks.append(outcome)
                    elif event.event_type == "NAVIGATION_ADJUSTED":
                        category = (
                            "yield"
                            if event.payload["message"].startswith("Yielded")
                            else "detour"
                        )
                        navigation[category] += 1
                for agent in engine.world.agents.values():
                    if agent.alive:
                        hunger += agent.hunger
                        alive_samples += 1
            final_hash = state_hash(engine.world)
            assert state_hash(store.replay(engine.run_id)) == final_hash
            assert (
                state_hash(store.replay(engine.run_id, use_snapshot=True)) == final_hash
            )
            result = {
                "seed": seed,
                "ticks": args.ticks,
                "alive": sum(a.alive for a in engine.world.agents.values()),
                "mean_living_hunger": round(hunger / max(1, alive_samples), 2),
                "actions": dict(actions),
                "rejections": dict(rejected),
                "task_outcomes": dict(outcomes),
                "navigation": dict(navigation),
                "successful_task_means": {
                    "ticks": round(
                        sum(
                            o["ended_tick"] - o["started_tick"]
                            for o in successful_tasks
                        )
                        / len(successful_tasks),
                        2,
                    ),
                    "action_energy": round(
                        sum(o["energy_spent"] for o in successful_tasks)
                        / len(successful_tasks),
                        2,
                    ),
                }
                if successful_tasks
                else {},
                "verified_skills": sum(
                    len(getattr(a, "skills", {})) for a in engine.world.agents.values()
                ),
                "completed_buildings": sum(
                    b.progress == 100 for b in engine.world.buildings.values()
                ),
                "mean_tick_ms": round(elapsed * 1000 / args.ticks, 2),
                "state_bytes": len(
                    json.dumps(authoritative_state(engine.world)).encode()
                ),
                "memory_counts": {
                    a.id: {
                        "short": len(a.memory.short_term),
                        "long": len(a.memory.long_term),
                        "facts": len(a.memory.facts),
                        "lessons": len(a.memory.lessons),
                    }
                    for a in engine.world.agents.values()
                    if getattr(a, "memory", None) is not None
                },
                "replay_verified": True,
            }
            results.append(result)
            print(json.dumps(result), flush=True)
        finally:
            store.close()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
