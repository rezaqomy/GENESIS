"""Bounded, isolated observations of invention; never mutates the running world."""

import argparse
import json
from collections import Counter
from pathlib import Path

from app.simulation.engine.core import Engine
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import WorldConfig
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


def evaluate(seed, ticks):
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True, seed=seed), store, UtilityPolicy())
    counts, examples = Counter(), {}
    for _ in range(ticks):
        for event in e.tick():
            if event.event_type == "ACTION_RESOLVED":
                action = str(event.payload["action"])
                counts[action] += 1
                if action in ("EXPERIMENT_ASSEMBLY", "ASSEMBLE", "OPERATE", "HEAT", "ACCEPT_TRADE"):
                    examples[action] = event.payload["message"]
    result = {
        "seed": seed, "ticks": ticks, "policy": "UtilityPolicy; no model calls or seeded recipes",
        "alive": sum(a.alive for a in e.world.agents.values()), "actions": dict(counts),
        "trials": sum(len(a.workshop.trials) if a.workshop else 0 for a in e.world.agents.values()),
        "devices": [{"name": b.assembly.design.name, "measured": b.assembly.measured,
                     "food_produced": b.food} for b in e.world.buildings.values() if b.assembly],
        "products": {a.name: a.inventory.products for a in e.world.agents.values() if a.inventory.products},
        "examples": examples, "replay_matches": state_hash(store.replay(e.run_id)) == state_hash(e.world),
    }
    store.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=240)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 7])
    args = parser.parse_args()
    results = []
    for seed in args.seeds:
        result = evaluate(seed, args.ticks)
        results.append(result)
        print(json.dumps(result), flush=True)
    Path("docs/evaluations/creativity.json").write_text(json.dumps(results, indent=2))
