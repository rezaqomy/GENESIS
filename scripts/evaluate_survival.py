"""Run actual autonomous villages across days, retaining compact survival evidence."""

import argparse
import collections
import gc
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.simulation.chunks.access import WorldAccess  # noqa: E402
from app.simulation.engine.core import Engine  # noqa: E402
from app.simulation.events.reducer import authoritative_state, state_hash  # noqa: E402
from app.simulation.models.domain import WorldConfig, WorldState  # noqa: E402
from app.simulation.persistence.sqlite import EventStore  # noqa: E402
from app.simulation.policies.utility import UtilityPolicy  # noqa: E402


def evaluate(seed, ticks, checkpoint=None):
    with tempfile.TemporaryDirectory(prefix="genesis-survival-") as directory:
        store = EventStore(str(Path(directory) / "world.sqlite"))
        e = Engine(WorldConfig(infinite=True, seed=seed), store, UtilityPolicy())
        if checkpoint:
            e.world = WorldState.model_validate(checkpoint)
            e.access = WorldAccess(e.world)
            store.append(
                [e.event("WORLD_CREATED", {"state": authoritative_state(e.world)})],
                e.world,
            )
        initial_tick = e.world.tick
        actions, goals, deaths, days = (
            collections.Counter(),
            collections.Counter(),
            [],
            [],
        )
        positions = {a.id: set() for a in e.world.agents.values()}
        for tick in range(ticks):
            for event in e.tick():
                if event.event_type == "ACTION_RESOLVED":
                    actions[event.payload["action"]] += 1
                    goal = (event.payload.get("intent", {}).get("decision") or {}).get(
                        "selected_goal"
                    )
                    goals[goal] += 1
                elif event.event_type == "AGENT_DIED":
                    deaths.append(
                        {"tick": event.tick, "agent": event.actor_id, **event.payload}
                    )
            for a in e.world.agents.values():
                positions[a.id].add((a.position.x, a.position.y))
            if e.world.tick % 240 == 0:
                row = {
                    "day": e.world.tick // 240,
                    "alive": sum(a.alive for a in e.world.agents.values()),
                    "food": e.world.settlements["settlement-0"].storage.food,
                    "water": e.world.settlements["settlement-0"].storage.water,
                    "farm_yield": sum(
                        b.food for b in e.world.buildings.values() if b.kind == "farm"
                    ),
                }
                days.append(row)
                print(json.dumps({"seed": seed, **row}), flush=True)
        replay_matches = state_hash(e.world) == state_hash(
            store.replay(e.run_id, use_snapshot=True)
        )
        result = {
            "policy_revision": "after_route_loop_fix",
            "scenario": "checkpoint_recovery" if checkpoint else "fresh_world",
            "seed": seed,
            "initial_tick": initial_tick,
            "ticks": e.world.tick,
            "days": days,
            "deaths": deaths,
            "actions": dict(actions),
            "goals": dict(goals),
            "visited_tiles_per_agent": {
                key: len(value) for key, value in positions.items()
            },
            "replay_matches": replay_matches,
        }
        store.close()
        del e, store
        gc.collect()
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=2400)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 7])
    parser.add_argument(
        "--output", type=Path, default=Path("docs/evaluations/survival-balance.json")
    )
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    checkpoint = json.loads(args.checkpoint.read_text()) if args.checkpoint else None
    seeds = [checkpoint["config"]["seed"]] if checkpoint else args.seeds
    results = [evaluate(seed, args.ticks, checkpoint) for seed in seeds]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n")
    assert all(r["replay_matches"] for r in results)
