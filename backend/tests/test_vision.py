"""Perception boundaries must hold for policy inputs and memory, independently of camera."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.simulation.chunks.access import WorldAccess
from app.simulation.engine.generation import generate_world
from app.simulation.events.reducer import agent_state, state_hash
from app.simulation.models.domain import Agent, Building, Position, WorldConfig
from app.simulation.observation.builder import build_observation
from app.simulation.policies.utility import UtilityPolicy
from app.simulation.settlements.environment import experience_tick


@pytest.mark.parametrize("infinite", [False, True])
def test_each_agent_has_bounded_sight_including_boundary(infinite):
    world = generate_world(WorldConfig(infinite=infinite))
    a, b, c = list(world.agents.values())[:3]
    a.position = Position(x=5, y=5)
    a.vision_radius = 2
    b.position = Position(x=7, y=5)
    c.position = Position(x=8, y=5)
    o = build_observation(world, a.id)
    assert o.vision_radius == 2
    assert b.id in {p["id"] for p in o.peers}
    assert c.id not in {p["id"] for p in o.peers}
    assert all(a.position.distance(t.position) <= 2 for t in o.tiles)
    assert all(a.position.distance(r.position) <= 2 for r in o.resources)
    assert all(a.position.distance(p) <= 2 for p in o.occupied)
    assert build_observation(world, a.id, radius=50).vision_radius == 2
    assert build_observation(world, a.id, radius=1).vision_radius == 1
    assert build_observation(world, b.id).vision_radius == 8


def test_remote_membership_is_not_a_live_information_feed():
    w = generate_world(WorldConfig(infinite=True))
    a = w.agents["agent-00"]
    a.position = Position(x=40, y=40)
    before = build_observation(w, a.id)
    assert before.settlement is None
    s = w.settlements[a.settlement_id]
    s.storage.food += 15
    s.resource_availability = 0
    w.buildings["remote"] = Building(
        id="remote", kind="shelter", position=s.center, settlement_id=s.id, progress=100
    )
    after = build_observation(w, a.id)
    assert after == before
    assert UtilityPolicy().decide(after) == UtilityPolicy().decide(before)
    a.position = s.center.model_copy()
    local = build_observation(w, a.id)
    assert local.settlement["storage"]["food"] == s.storage.food
    assert "members" not in local.settlement
    assert "resource_availability" not in local.settlement
    assert "buildings" not in local.settlement
    assert "remote" in {b["id"] for b in local.buildings}


def test_tower_bonus_is_bounded_and_shared_with_memory():
    w = generate_world(WorldConfig(infinite=True))
    a = w.agents["agent-00"]
    access = WorldAccess(w)
    food = next(r for r in access.visible_resources(Position(x=0, y=0), 20) if r.kind == "food")
    a.position = food.position.model_copy()
    a.vision_radius = 2
    w.buildings["tower"] = Building(
        id="tower", kind="watchtower", position=a.position, progress=100
    )
    o = build_observation(w, a.id)
    assert o.vision_radius == 6
    experience_tick(w, access)
    assert a.memory.facts
    assert all(a.position.distance(f.position) <= 6 for f in a.memory.facts.values())
    a.vision_radius = 12
    assert build_observation(w, a.id).vision_radius == 12
    w.buildings["tower"].durability = 0
    a.vision_radius = 2
    assert build_observation(w, a.id).vision_radius == 2


def test_unseen_food_changes_do_not_refresh_memories_or_social_contacts():
    w = generate_world(WorldConfig(infinite=True))
    a = w.agents["agent-00"]
    access = WorldAccess(w)
    food = next(r for r in access.visible_resources(Position(x=0, y=0), 20) if r.kind == "food")
    a.position = food.position.model_copy()
    a.vision_radius = 2
    experience_tick(w, access)
    assert a.memory.facts
    facts = {k: f.model_copy(deep=True) for k, f in a.memory.facts.items()}
    a.position = Position(x=40, y=40)
    access.harvest(food, food.quantity)
    a.discoveries = []
    w.tick += 1
    experience_tick(w, access)
    assert not a.nearby_agents
    for key, fact in facts.items():
        assert a.memory.facts[key] == fact
    assert all(a.position.distance(p) <= 2 for p in a.discoveries)
    o = build_observation(w, a.id)
    assert all(a.position.distance(r.position) <= 2 for r in o.resources)
    assert all(a.position.distance(p) <= 2 for p in o.self_agent.discoveries)
    a.position = food.position.model_copy()
    w.tick += 1
    experience_tick(w, access)
    assert a.memory.facts[food.id].quantity == 0
    assert a.memory.facts[food.id].observed_tick == w.tick


def test_new_vision_default_preserves_historical_agent_serialization():
    w = generate_world(WorldConfig(infinite=True))
    data = agent_state(w.agents["agent-00"])
    data.pop("vision_radius", None)
    old = Agent.model_validate(data)
    assert old.vision_radius == 8
    assert agent_state(old) == data
    old.vision_radius = 3
    assert agent_state(old)["vision_radius"] == 3


def test_observation_api_matches_policy_input_without_changing_world():
    with TestClient(create_app(":memory:")) as client:
        svc = client.app.state.simulation
        before = state_hash(svc.engine.world)
        response = client.get("/api/agents/agent-00/observation")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == svc.engine.run_id
        assert data["observation"] == build_observation(
            svc.engine.world, "agent-00", access=svc.engine.access
        ).model_dump(mode="json")
        assert state_hash(svc.engine.world) == before
        assert client.get("/api/agents/missing/observation").status_code == 404
        a = svc.engine.world.agents["agent-00"]
        a.alive = False
        o = build_observation(svc.engine.world, a.id)
        assert o.vision_radius == 0
        assert not o.tiles and not o.resources and not o.peers and not o.buildings


def test_construction_completion_outside_sight_is_not_reported():
    from app.simulation.models.domain import Action, AgentIntent, TaskPlan
    from app.simulation.planning.tasks import update_task

    w = generate_world(WorldConfig(infinite=True))
    a = w.agents["agent-00"]
    target = Position(x=2, y=2)
    a.position = Position(x=40, y=40)
    a.task = TaskPlan(
        id="local-project",
        kind="construction",
        context="day:safe",
        stage="build",
        started_tick=0,
        last_progress_tick=0,
        deadline=120,
        origin=a.position,
        target=target,
        building_kind="shelter",
        work_units=1,
    )
    w.buildings["finished"] = Building(id="finished", kind="shelter", position=target, progress=100)
    intent = AgentIntent(actor_id=a.id, action=Action.IDLE)
    assert update_task(w, a, intent, True, None, 1) is None
    assert a.task.status == "active"
    a.position = Position(x=2, y=3)
    assert update_task(w, a, intent, True, None, 2).status == "succeeded"
