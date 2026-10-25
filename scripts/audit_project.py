"""Isolated diagnostic probes; never opens or changes the application's database.

These record current behavior rather than assert that known defects stay present.
Model responses are mocked; the scheduling probe uses actual asyncio timers.
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.simulation import SimulationService  # noqa: E402
from app.simulation.actions.construction import storage_access  # noqa: E402
from app.simulation.cognition.memory import experience  # noqa: E402
from app.simulation.cognition.runtime import Choice, CognitionPolicy, Settings  # noqa: E402
from app.simulation.cognition.tiers import action_snapshot  # noqa: E402
from app.simulation.engine.core import Engine  # noqa: E402
from app.simulation.events.reducer import state_hash  # noqa: E402
from app.simulation.models.domain import (  # noqa: E402
    Action,
    Agent,
    AgentIntent,
    Building,
    Position,
    Resource,
    Terrain,
    Tile,
    WorldConfig,
)
from app.simulation.observation.builder import build_observation  # noqa: E402
from app.simulation.persistence.sqlite import EventStore  # noqa: E402
from app.simulation.policies.utility import UtilityPolicy  # noqa: E402


def synchronous_probes():
    results = {}
    store = EventStore(":memory:")
    try:
        # Controlled flat finite fixture, deliberately exercising the same UtilityPolicy
        # and full Engine cooldown handling used by infinite worlds.
        engine = Engine(WorldConfig(), store, UtilityPolicy())
        actor = Agent(
            id="agent-00",
            name="Probe",
            age=25,
            visual_color="#fff",
            position=Position(x=2, y=2),
            hunger=85,
            energy=1,
        )
        engine.world.agents = {actor.id: actor}
        engine.world.tiles = [
            Tile(position=Position(x=x, y=y), terrain=Terrain.GRASS, walkable=True)
            for y in range(30)
            for x in range(40)
        ]
        engine.world.resources = {
            "food": Resource(
                id="food",
                position=Position(x=5, y=2),
                kind="food",
                quantity=8,
                capacity=8,
            )
        }
        trace = []
        for _ in range(16):
            events = engine.tick()
            trace.extend(
                {
                    "tick": e.tick,
                    "type": e.event_type,
                    "action": e.payload["action"],
                    "message": e.payload["message"],
                }
                for e in events
                if e.event_type in ("ACTION_REJECTED", "ACTION_RESOLVED")
            )
        results["urgent_low_energy"] = {
            "fixture": "flat finite world with UtilityPolicy and full Engine",
            "alive": actor.alive,
            "hunger": actor.hunger,
            "trace": trace,
        }
    finally:
        store.close()

    store = EventStore(":memory:")
    try:
        engine = Engine(WorldConfig(infinite=True), store)
        actor = engine.world.agents["agent-00"]
        settlement = engine.world.settlements["settlement-0"]
        building = Building(
            id="destroyed-storage",
            kind="storage",
            position=Position(x=50, y=50),
            progress=100,
            durability=0,
            settlement_id=settlement.id,
        )
        engine.world.buildings[building.id] = building
        settlement.buildings.append(building.id)
        actor.position = building.position.model_copy()
        results["destroyed_storage"] = {
            "durability": building.durability,
            "distance_to_center": actor.position.distance(settlement.center),
            "grants_access": storage_access(engine.world, actor) is not None,
        }

        actor.thought = "Old model explanation"
        intent = AgentIntent(actor_id=actor.id, action=Action.IDLE)
        experience(
            engine.world, actor, intent, True, "waited", 1, action_snapshot(actor)
        )
        results["stale_explanation"] = {
            "current_source": actor.cognition_source,
            "retained_thought": actor.thought,
        }
    finally:
        store.close()

    store = EventStore(":memory:")
    try:
        engine = Engine(WorldConfig(infinite=True), store)

        def failed_append(*args, **kwargs):
            raise sqlite3.OperationalError("Injected persistence failure")

        try:
            with patch.object(store, "append", failed_append):
                engine.tick()
        except sqlite3.OperationalError:
            restored = store.replay(engine.run_id)
            results["persistence_failure"] = {
                "live_tick": engine.world.tick,
                "persisted_tick": restored.tick,
                "hash_matches": state_hash(engine.world) == state_hash(restored),
                "live_sequence": engine.sequence,
                "persisted_sequence": store.sequence(engine.run_id),
            }
    finally:
        store.close()
    return results


async def asynchronous_probes():
    results = {}
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    observations = [
        build_observation(engine.world, aid, access=engine.access)
        for aid in list(engine.world.agents)[:2]
    ]
    policy = CognitionPolicy(
        UtilityPolicy(),
        Settings(dialogue_url="https://unused.invalid", dialogue_model="mock"),
    )
    policy.reset(engine.run_id)
    release, entered = asyncio.Event(), asyncio.Event()
    calls = []

    async def local_choices(*args):
        calls.append(1)
        return [Choice(goal="socialize", reason="mock") for _ in observations]

    async def blocked_speech(*args):
        entered.set()
        await release.wait()
        return None, None

    try:
        with patch("app.simulation.cognition.laya.choose_batch", local_choices):
            with patch.object(policy, "speak", blocked_speech):
                policy.decide_batch(observations)
                await asyncio.wait_for(entered.wait(), timeout=5)
                published = len(policy.results)
                newer = [
                    o.model_copy(update={"tick": 10}, deep=True) for o in observations
                ]
                policy.decide_batch(newer)
                await asyncio.gather(*list(policy.tasks.values()))
                results["dialogue_blocks_refresh"] = {
                    "local_batches_started": len(calls),
                    "choices_published_before_speech": published,
                    "pending_task_keys": list(policy.tasks),
                    "dialogue_task_keys": list(getattr(policy, "dialogue_tasks", {})),
                    "new_local_batch_started": len(calls) > 1,
                }
                release.set()
                await asyncio.gather(
                    *list(getattr(policy, "dialogue_tasks", {}).values())
                )
    finally:
        await policy.close()
        store.close()

    with patch.dict(os.environ, {"GENESIS_COGNITION": "0"}):
        service = SimulationService(":memory:", WorldConfig(infinite=True))
    service.start()
    try:
        slow_client = asyncio.Queue(maxsize=1)
        service.subscribers.add(slow_client)
        published = []
        for index in range(300):
            event = service.engine.event("AUDIT_MESSAGE", {"message": f"probe {index}"})
            service.store.append([event])
            service.publish([event])
            published.append(event.event_id)
        packet = slow_client.get_nowait()
        recoverable = {e["event_id"] for e in service.recent}
        backfill = service.store.journal(
            service.engine.run_id, 0, service.engine.sequence
        )
        results["slow_client_journal"] = {
            "published_events": len(published),
            "events_in_latest_packet": len(packet["events"]),
            "events_in_recent_resync_window": len(recoverable),
            "unrecoverable_without_event_api": len(set(published) - recoverable),
            "event_api_rows": len(service.store.events(service.engine.run_id)),
            "unrecovered_after_journal_backfill": len(
                set(published) - {event.event_id for event in backfill}
            ),
        }
        service.subscribers.discard(slow_client)
        await service.submit("start")
        for _ in range(14):
            await asyncio.sleep(0.05)
            await service.submit("speed", 1)
        busy_tick = service.engine.world.tick
        await asyncio.sleep(0.56)
        results["command_starvation"] = {
            "commands": 14,
            "command_interval_ms": 50,
            "busy_period_ms_at_least": 700,
            "tick_after_busy_period": busy_tick,
            "tick_after_quiet_period": service.engine.world.tick,
        }
    finally:
        await service.close()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = synchronous_probes() | asyncio.run(asynchronous_probes())
    encoded = json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
