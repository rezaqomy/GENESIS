"""Evaluate autonomous communal work with UtilityPolicy in isolated seeded worlds."""

import json
from collections import Counter
from pathlib import Path

from app.simulation.engine.core import Engine
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import WorldConfig
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


def evaluate(seed, ticks=240):
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True, seed=seed), store, UtilityPolicy())
    actions, projects = Counter(), []
    for _ in range(ticks):
        events = e.tick()
        for event in events:
            if event.event_type == "ACTION_RESOLVED":
                actions[event.payload["action"]] += 1
            if event.event_type.startswith("COMMUNITY_PROJECT_"):
                projects.append(event.payload["message"])
    s = next(iter(e.world.settlements.values()))
    result = {
        "seed": seed,
        "ticks": ticks,
        "policy": "UtilityPolicy (no model calls)",
        "alive": sum(a.alive for a in e.world.agents.values()),
        "actions": dict(actions),
        "community": s.community.model_dump(mode="json") if s.community else None,
        "project_events": projects,
        "farm_yield": sum(
            b.food for b in e.world.buildings.values() if b.kind == "farm"
        ),
        "replay_matches": state_hash(store.replay(e.run_id)) == state_hash(e.world),
    }
    store.close()
    return result


if __name__ == "__main__":
    results = []
    for seed in (42, 7, 19):
        result = evaluate(seed)
        results.append(result)
        print(json.dumps(result), flush=True)
    Path("docs/evaluations/community.json").write_text(json.dumps(results, indent=2))
