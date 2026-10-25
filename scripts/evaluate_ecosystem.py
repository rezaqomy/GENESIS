"""Observe autonomous use in an isolated world; no forced actions or LLM calls."""

import argparse
import json
from collections import Counter
from pathlib import Path

from app.simulation.engine.core import Engine
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import WorldConfig
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


def evaluate(seed, ticks, agents):
    store = EventStore(":memory:")
    engine = Engine(
        WorldConfig(infinite=True, seed=seed, agent_count=agents),
        store,
        UtilityPolicy(),
    )
    counts, rejected, examples = Counter(), Counter(), {}
    for i in range(ticks):
        for event in engine.tick():
            if event.event_type == "ACTION_RESOLVED":
                action = str(event.payload["action"])
                counts[action] += 1
                examples[action] = event.payload["message"]
            elif event.event_type == "ACTION_REJECTED":
                rejected[event.payload["message"]] += 1
        if (i + 1) % 240 == 0:
            print(
                json.dumps({"progress": i + 1, "seed": seed, "actions": dict(counts)}),
                flush=True,
            )
    w = engine.world
    result = {
        "seed": seed,
        "ticks": ticks,
        "agents": agents,
        "policy": "UtilityPolicy; no LLM, forced actions, starting crops or tame animals",
        "alive": sum(a.alive for a in w.agents.values()),
        "animals": len(w.ecosystem.animals),
        "crops": len(w.ecosystem.crops),
        "tame": sum(v.owner_id is not None for v in w.ecosystem.animals.values()),
        "juveniles": sum(
            w.tick - v.born_tick < 240 for v in w.ecosystem.animals.values()
        ),
        "actions": dict(counts),
        "rejected": dict(rejected),
        "examples": {
            k: v
            for k, v in examples.items()
            if k
            in {
                "TILL",
                "PLANT",
                "WATER_CROP",
                "HARVEST",
                "FEED",
                "BREED",
                "COLLECT",
                "ATTACK",
                "STEAL",
                "PICK_UP",
            }
        },
        "replay_matches": state_hash(store.replay(engine.run_id)) == state_hash(w),
    }
    store.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agents", type=int, default=10)
    args = parser.parse_args()
    result = evaluate(args.seed, args.ticks, args.agents)
    path = Path(f"docs/evaluations/ecosystem-{args.seed}.json")
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
