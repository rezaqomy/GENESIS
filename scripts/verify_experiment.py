"""Run an actual bounded utility experiment and verify full/snapshot replay."""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.simulation.engine.core import Engine  # noqa: E402
from app.simulation.events.reducer import state_hash  # noqa: E402
from app.simulation.models.domain import WorldConfig  # noqa: E402
from app.simulation.persistence.sqlite import EventStore  # noqa: E402
from app.simulation.policies.utility import UtilityPolicy  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--ticks", type=int, default=700)
parser.add_argument("--seed", type=int, default=42)
args = parser.parse_args()
store = EventStore(":memory:")
try:
    engine = Engine(WorldConfig(infinite=True, seed=args.seed), store, UtilityPolicy())
    initial_chunks = {f"{cx},{cy}" for cx in (-1,0) for cy in (-1,0)}
    distances = {key: 0 for key in engine.world.agents}
    departed, returned = set(), set()
    actions = Counter()
    for i in range(args.ticks):
        for event in engine.tick():
            if event.event_type == "ACTION_RESOLVED":
                actions[event.payload["action"]] += 1
        for key, agent in engine.world.agents.items():
            distances[key] = max(distances[key], agent.position.distance(agent.home))
            if f"{agent.position.x // 32},{agent.position.y // 32}" not in initial_chunks:
                departed.add(key)
            if key in departed and agent.position.distance(agent.home) < 9:
                returned.add(key)
        if (i+1) % 100 == 0:
            print(f"Tick {i+1}: alive={sum(a.alive for a in engine.world.agents.values())}, "
                  f"new-region explorers={len(departed)}, returned={len(returned)}", flush=True)
    final_hash = state_hash(engine.world)
    assert final_hash == state_hash(store.replay(engine.run_id))
    assert final_hash == state_hash(store.replay(engine.run_id, use_snapshot=True))
    print("Accepted actions:", dict(sorted(actions.items())))
    print("Farthest Manhattan distances:", distances)
    print("Beyond initial chunks:", sorted(departed), "Returned:", sorted(returned))
    print("Completed structures:", [b.kind for b in engine.world.buildings.values() if b.progress == 100])
    print("Bounded loaded chunks:", len(engine.access.cache.entries))
    print("Full-log and snapshot replay verified:", final_hash)
finally:
    store.close()
