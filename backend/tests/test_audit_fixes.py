import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.simulation import SimulationService
from app.simulation.actions.construction import storage_access
from app.simulation.actions.resolver import resolve_intent, validate_intent
from app.simulation.cognition.memory import experience
from app.simulation.cognition.runtime import Choice, CognitionPolicy, Settings
from app.simulation.cognition.tiers import action_snapshot
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import (
    Action,
    AgentIntent,
    Building,
    Position,
    WorldConfig,
)
from app.simulation.observation.builder import build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


@pytest.mark.parametrize("operation", ["tick", "step", "reset", "speed"])
def test_failed_write_restores_world_sequence_and_log(monkeypatch, operation):
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(), store)
    before_hash, before_run, before_sequence = (
        state_hash(engine.world),
        engine.run_id,
        engine.sequence,
    )
    append = store.append

    def fail(events, snapshot=None):
        # Fail *after* SQL writes: outer transaction must roll these back too.
        append(events, snapshot)
        raise sqlite3.OperationalError("injected failure")

    monkeypatch.setattr(store, "append", fail)
    with pytest.raises(sqlite3.OperationalError):
        if operation == "tick":
            engine.tick()
        elif operation == "reset":
            engine.reset(WorldConfig(seed=7), record_command=True)
        else:
            engine.command(operation, 2 if operation == "speed" else None)
    assert engine.run_id == before_run
    assert engine.sequence == before_sequence
    assert state_hash(engine.world) == before_hash
    assert state_hash(store.replay(before_run)) == before_hash
    assert store.sequence(before_run) == before_sequence
    assert store.latest_run() == before_run
    monkeypatch.setattr(store, "append", append)
    engine.tick()
    assert state_hash(engine.world) == state_hash(store.replay(before_run))
    store.close()


def test_step_command_and_tick_share_one_transaction(monkeypatch):
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(), store)
    before = state_hash(engine.world)
    append, calls = store.append, []

    def fail_tick(events, snapshot=None):
        calls.append(1)
        append(events, snapshot)
        if len(calls) == 2:
            raise sqlite3.OperationalError("tick failed after command was inserted")

    monkeypatch.setattr(store, "append", fail_tick)
    with pytest.raises(sqlite3.OperationalError):
        engine.command("step")
    assert engine.sequence == store.sequence(engine.run_id) == 1
    assert state_hash(engine.world) == state_hash(store.replay(engine.run_id)) == before
    store.close()


@pytest.mark.asyncio
async def test_commands_do_not_starve_ticks_and_pause_stays_responsive():
    service = SimulationService(":memory:", WorldConfig(agent_count=1))
    service.start()
    try:
        await service.submit("start")
        for index in range(18):
            await asyncio.sleep(0.04)
            await service.submit("speed", 1 if index % 2 else 2)
        assert service.engine.world.tick >= 1
        await service.submit("pause")
        tick = service.engine.world.tick
        await asyncio.sleep(0.3)
        assert service.engine.world.tick == tick
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_writer_failure_retains_committed_state_and_closes(monkeypatch):
    service = SimulationService(":memory:", WorldConfig(agent_count=1))
    before = state_hash(service.engine.world)
    service.start()

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("injected failure")

    monkeypatch.setattr(service.store, "append", fail)
    with pytest.raises(RuntimeError, match="writer stopped"):
        await service.submit("step")
    assert service.task.done() and service.failure == "OperationalError"
    assert state_hash(service.engine.world) == before
    await service.close()
    with pytest.raises(sqlite3.ProgrammingError):
        service.store.connection.execute("SELECT 1")


@pytest.mark.asyncio
async def test_slow_dialogue_does_not_block_choices_or_replace_newer_choice(monkeypatch):
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store)
    o = build_observation(engine.world, "agent-00", access=engine.access)
    policy = CognitionPolicy(
        UtilityPolicy(), Settings(dialogue_url="https://unused.invalid", dialogue_model="mock")
    )
    policy.reset(engine.run_id)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def choices(*args):
        calls.append(1)
        return [Choice(goal="socialize" if len(calls) == 1 else "rest", reason="mock")]

    async def speech(*args):
        entered.set()
        await release.wait()
        return "agent-01", "Old speech"

    monkeypatch.setattr("app.simulation.cognition.laya.choose_batch", choices)
    monkeypatch.setattr(policy, "speak", speech)
    try:
        policy.decide_batch([o])
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.gather(*list(policy.tasks.values()))
        assert policy.dialogue_tasks and not policy.tasks
        newer = o.model_copy(update={"tick": 10}, deep=True)
        policy.decide_batch([newer])
        await asyncio.gather(*list(policy.tasks.values()))
        assert len(calls) == 2
        release.set()
        await asyncio.gather(*list(policy.dialogue_tasks.values()))
        result = policy.results[o.self_agent.id]
        assert result[1] == 10 and result[2].goal == "rest" and result[4] is None
    finally:
        await policy.close()
        store.close()


def test_urgent_hunger_recovers_before_impossible_movement_and_eats_if_carried():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store)
    actor = engine.world.agents["agent-00"]
    actor.hunger, actor.energy, actor.inventory.food = 95, 0, 0
    observation = build_observation(engine.world, actor.id, access=engine.access)
    intent = UtilityPolicy().decide(observation)
    assert intent.action == Action.REST
    assert validate_intent(engine.world, intent, engine.access) is None
    observation.self_agent.inventory.food = 1
    assert UtilityPolicy().decide(observation).action == Action.EAT
    store.close()


def test_destroyed_storage_cannot_be_used_and_reconstruction_requires_materials():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store)
    actor = engine.world.agents["agent-00"]
    settlement = engine.world.settlements[actor.settlement_id]
    target = Position(x=50, y=50)
    broken = Building(
        id="broken",
        kind="storage",
        position=target,
        progress=100,
        durability=0,
        settlement_id=settlement.id,
    )
    engine.world.buildings[broken.id] = broken
    settlement.buildings.append(broken.id)
    actor.position = target.model_copy()
    assert storage_access(engine.world, actor) is None
    intent = AgentIntent(
        actor_id=actor.id, action=Action.BUILD, target=target, building_kind="storage"
    )
    assert (
        validate_intent(engine.world, intent, engine.access)
        == "Insufficient reconstruction materials"
    )
    actor.inventory.wood = 4
    for _ in range(4):
        assert resolve_intent(engine.world, intent, engine.access)[0]
    assert actor.inventory.wood == 0 and broken.progress == broken.durability == 100
    assert storage_access(engine.world, actor) is settlement
    store.close()


def test_fallback_clears_obsolete_model_explanation():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store)
    actor = engine.world.agents["agent-00"]
    actor.thought = "Previous model decision"
    intent = AgentIntent(actor_id=actor.id, action=Action.IDLE)
    experience(engine.world, actor, intent, True, "waited", 1, action_snapshot(actor))
    assert actor.cognition_source == "utility" and actor.thought == ""
    store.close()


def test_journal_backfill_is_bounded_and_includes_events_outside_resync_window():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(), store)
    events = []
    for index in range(1700):
        events.append(engine.event("MESSAGE", {"message": f"event {index}", "intent": "private"}))
        events.append(engine.event("INTERNAL", {}))
    store.append(events)
    through = events[-1].sequence_number
    journal = store.journal(engine.run_id, 0, through)
    assert len(journal) == 1500 and journal[-1].payload["message"] == "event 1699"
    assert journal[0].payload["message"] == "event 200"
    assert len(store.journal(engine.run_id, through - 10, through)) == 5
    store.close()


def test_journal_api_uses_watermark_and_only_returns_readable_fields(monkeypatch):
    monkeypatch.setenv("GENESIS_INFINITE", "0")
    with TestClient(create_app(":memory:")) as client:

        async def seed_journal():
            service = client.app.state.simulation
            events = [
                service.engine.event("MESSAGE", {"message": str(index), "intent": "private"})
                for index in range(300)
            ]
            service.store.append(events)
            return events[-1].sequence_number

        watermark = client.portal.call(seed_journal)
        response = client.get(f"/api/journal?through={watermark}&limit=300").json()
        assert response["next_sequence"] == watermark
        assert len(response["events"]) == 300
        assert all(list(e["payload"]) == ["message"] for e in response["events"])
        empty = client.get(f"/api/journal?after={watermark}").json()
        assert empty["events"] == [] and empty["next_sequence"] == watermark


def test_resource_only_perception_matches_full_view_without_materializing_tiles(monkeypatch):
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store)
    access = engine.access
    center = Position(x=-1, y=-1)
    _, expected = access.visible(center, 12)
    expected = [resource.model_dump() for resource in expected]

    def unexpected_tile(*args):
        raise AssertionError("Resource-only observation should not allocate tiles")

    monkeypatch.setattr(access, "tile", unexpected_tile)
    assert [r.model_dump() for r in access.visible_resources(center, 12)] == expected
    store.close()
