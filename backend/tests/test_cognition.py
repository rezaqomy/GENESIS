import asyncio
import json

import httpx
import pytest

from app.simulation.actions.resolver import validate_intent
from app.simulation.cognition.runtime import Choice, CognitionPolicy, Settings
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import Action, AgentIntent, Position, WorldConfig
from app.simulation.observation.builder import build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


def fixture_world():
    store = EventStore(":memory:")
    return Engine(WorldConfig(infinite=True), store, UtilityPolicy()), store


@pytest.mark.asyncio
async def test_async_routing_memory_and_replay():
    engine, store = fixture_world()
    a, b = list(engine.world.agents.values())[:2]
    # Record a scenario's starting state so full replay includes these positions.
    a.position = Position(x=0, y=0)
    b.position = Position(x=1, y=0)
    a.psychology.loneliness = 0.9
    a.personality.sociability = 1
    from app.simulation.events.reducer import authoritative_state

    store.connection.execute(
        "UPDATE snapshots SET state=?, state_hash=? WHERE run_id=? AND sequence_number=?",
        (
            json.dumps(authoritative_state(engine.world)),
            state_hash(engine.world),
            engine.run_id,
            engine.sequence,
        ),
    )
    store.connection.commit()
    policy = CognitionPolicy(
        engine.policy,
        Settings(
            provider="ollama",
            dialogue_url="https://dialogue.test/v1",
            dialogue_model="future-model",
        ),
    )
    policy.reset(engine.run_id)
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append((str(request.url), body))
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {"goal": "socialize", "reason": "I feel lonely and want company."}
                        )
                    }
                },
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"text":"How are you feeling today?"}'}}]},
        )

    await policy.client.aclose()
    policy.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    observation = build_observation(engine.world, a.id, access=engine.access)
    try:
        # Immediate fallback; inference does not mutate the observed world.
        policy.decide(observation)
        assert len(policy.tasks) == 1
        await asyncio.gather(*list(policy.tasks.values()))
        assert not a.memories
        intent = policy.decide(observation)
        assert intent.action == Action.SOCIALIZE
        assert intent.cognition_source.startswith("ollama:")
        assert intent.utterance
        events = engine.tick([intent])
        assert any(e.event_type == "DIALOGUE" for e in events)
        assert any(m.kind == "dialogue" for m in a.memories)
        assert any(m.kind == "dialogue" for m in b.memories)
        assert calls[0][1]["options"]["num_gpu"] == 0
        assert calls[1][0] == "https://dialogue.test/v1/chat/completions"
        assert state_hash(store.replay(engine.run_id, use_snapshot=True)) == state_hash(
            engine.world
        )
    finally:
        await policy.close()
        store.close()


@pytest.mark.asyncio
async def test_expiry_emergency_reset_and_malformed():
    engine, store = fixture_world()
    a = engine.world.agents["agent-00"]
    policy = CognitionPolicy(engine.policy, Settings(provider="ollama", enabled=False, ttl=2))
    policy.reset(engine.run_id)
    try:
        a.hunger, a.inventory.food = 95, 1
        o = build_observation(engine.world, a.id, access=engine.access)
        policy.results[a.id] = (
            engine.run_id,
            0,
            Choice(goal="explore", reason="curious"),
            None,
            None,
        )
        assert policy.decide(o).action == Action.EAT
        o.tick = 5
        policy.results[a.id] = (engine.run_id, 0, Choice(goal="eat", reason="hungry"), None, None)
        assert policy.decide(o).cognition_source == "utility"
        policy.results[a.id] = ("old-run", 5, Choice(goal="eat", reason="hungry"), None, None)
        assert policy.decide(o).cognition_source == "utility"
        await policy.client.aclose()
        policy.client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"message": {"content": "bad JSON"}})
            )
        )
        await policy.infer(engine.run_id, o, engine.policy.decide(o))
        assert policy.stats["errors"] == 1
        assert not policy.results
        policy.reset("new-run")
        assert not policy.results and not policy.tasks
    finally:
        await policy.close()
        store.close()


def test_dialogue_listener_validation_and_bounded_memory():
    engine, store = fixture_world()
    try:
        a, b = list(engine.world.agents.values())[:2]
        b.position = Position(x=100, y=100)
        intent = AgentIntent(
            actor_id=a.id, action=Action.SOCIALIZE, peer_id=b.id, utterance="Hello"
        )
        assert validate_intent(engine.world, intent)
        # Fresh run restores replayable initial state.
        engine.reset(WorldConfig(infinite=True))
        for _ in range(65):
            engine.tick([AgentIntent(actor_id="agent-00", action=Action.REST)])
        assert len(engine.world.agents["agent-00"].memories) == 48
        assert state_hash(store.replay(engine.run_id)) == state_hash(engine.world)
    finally:
        store.close()


@pytest.mark.asyncio
async def test_reset_cancels_pending_and_inference_is_fair():
    engine, store = fixture_world()
    policy = CognitionPolicy(engine.policy, Settings(provider="ollama", interval=1))
    policy.reset(engine.run_id)
    gate = asyncio.Event()

    async def handler(request):
        await gate.wait()
        return httpx.Response(
            200, json={"message": {"content": '{"goal":"find_food","reason":"supplies"}'}}
        )

    await policy.client.aclose()
    policy.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        for aid in sorted(engine.world.agents):
            policy.decide(build_observation(engine.world, aid, access=engine.access))
        assert list(policy.tasks) == ["agent-00"]
        gate.set()
        await asyncio.gather(*list(policy.tasks.values()))
        engine.world.tick = 1
        for aid in sorted(engine.world.agents):
            policy.decide(build_observation(engine.world, aid, access=engine.access))
        assert list(policy.tasks) == ["agent-01"]
        pending = list(policy.tasks.values())
        policy.reset("new-run")
        await asyncio.gather(*pending, return_exceptions=True)
        assert not policy.results
    finally:
        await policy.close()
        store.close()


@pytest.mark.asyncio
async def test_laya_batch_primary_retention_legality_and_replay():
    engine, store = fixture_world()
    policy = CognitionPolicy(engine.policy, Settings())
    policy.reset(engine.run_id)
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert request.url.path == "/decide-batch"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "goal": next(iter(row["criteria"])),
                        "probability": 0.8,
                        "device": "cpu",
                        "model": policy.settings.laya_model,
                    }
                    for row in body["requests"]
                ]
            },
        )

    await policy.client.aclose()
    policy.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        observations = [
            build_observation(engine.world, aid, access=engine.access)
            for aid in sorted(engine.world.agents)
        ]
        first = policy.decide_batch(observations)
        assert all(i.cognition_source == "utility" for i in first)
        assert len(policy.tasks) == 1
        await asyncio.gather(*list(policy.tasks.values()))
        assert len(calls[0]["requests"]) == len(observations)
        # Disable refresh to prove cached Laya choices continue directing legal actions.
        object.__setattr__(policy.settings, "enabled", False)
        second = policy.decide_batch(observations)
        third = policy.decide_batch(observations)
        assert all(i.cognition_source.startswith("laya:") for i in second + third)
        assert policy.stats["consumed"] == len(observations) * 2
        engine.tick(second)
        assert state_hash(store.replay(engine.run_id)) == state_hash(engine.world)
        # Unavailable and previous-run choices cannot override current planning.
        aid = observations[0].self_agent.id
        policy.results[aid] = (
            engine.run_id,
            0,
            Choice(goal="teleport", reason="invalid"),
            None,
            None,
        )
        assert policy.decide(observations[0]).cognition_source == "utility"
        policy.reset("another-run")
        assert not policy.results
    finally:
        await policy.close()
        store.close()
