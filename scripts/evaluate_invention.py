"""Observe autonomous invention without injecting recipes, designs or chosen actions."""

import argparse
import collections
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.simulation.engine.core import Engine  # noqa: E402
from app.simulation.events.reducer import state_hash  # noqa: E402
from app.simulation.models.domain import WorldConfig  # noqa: E402
from app.simulation.persistence.sqlite import EventStore  # noqa: E402
from app.simulation.policies.utility import UtilityPolicy  # noqa: E402


def evaluate(seed, ticks, count):
    with tempfile.TemporaryDirectory(prefix="genesis-invention-") as directory:
        store = EventStore(str(Path(directory) / "world.sqlite"))
        e = Engine(
            WorldConfig(infinite=True, seed=seed, agent_count=count),
            store,
            UtilityPolicy(),
        )
        actions, rejections = collections.Counter(), collections.Counter()
        for _ in range(ticks):
            for event in e.tick():
                if event.event_type == "ACTION_RESOLVED":
                    actions[event.payload["action"]] += 1
                if event.event_type == "ACTION_REJECTED":
                    rejections[event.payload["message"]] += 1
        result = {
            "seed": seed,
            "ticks": ticks,
            "agents": count,
            "policy": "autonomous UtilityPolicy; no forced hypotheses or extra materials; Laya not used",
            "actions": dict(actions),
            "rejections": dict(rejections),
            "agents_final": [
                {
                    "id": a.id,
                    "alive": a.alive,
                    "hunger": a.hunger,
                    "tool_trials": len(a.inventions.trials) if a.inventions else 0,
                    "designs": {
                        key: trial.model_dump(mode="json")
                        for key, trial in (
                            a.inventions.designs.items() if a.inventions else []
                        )
                    },
                    "failed_trials": sum(
                        max(t.performance.values()) < 0.3 for t in a.inventions.trials
                    )
                    if a.inventions
                    else 0,
                    "ongoing_steps": a.inventions.experiment_steps
                    if a.inventions
                    else 0,
                }
                for a in e.world.agents.values()
            ],
            "replay_matches": state_hash(e.world) == state_hash(store.replay(e.run_id)),
        }
        store.close()
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 19])
    parser.add_argument("--ticks", type=int, default=240)
    parser.add_argument("--agents", type=int, default=1)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/evaluations/invention.json")
    )
    args = parser.parse_args()
    results = []
    for seed in args.seeds:
        row = evaluate(seed, args.ticks, args.agents)
        results.append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(row), flush=True)
    assert all(r["replay_matches"] for r in results)
