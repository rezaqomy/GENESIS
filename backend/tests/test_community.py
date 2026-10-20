"""Cooperation needs physical effects, locality, and deterministic replay."""

import pytest

from app.simulation.actions.resolver import resolve_intent
from app.simulation.community import civic, record_work, update_projects
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import authoritative_state, settlement_state, state_hash
from app.simulation.models.domain import (
    Action,
    AgentIntent,
    Building,
    CommunityProject,
    Position,
    Settlement,
    WorldConfig,
)
from app.simulation.observation.builder import build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


@pytest.fixture
def engine():
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    yield e
    store.close()


def test_help_is_a_real_transfer_with_recipient_memory_and_range_validation(engine):
    a, b = list(engine.world.agents.values())[:2]
    a.position, b.position = Position(x=0, y=0), Position(x=1, y=0)
    a.inventory.food, b.inventory.food = 3, 0
    intent = AgentIntent(actor_id=a.id, action=Action.GIVE, peer_id=b.id, item="food")
    assert resolve_intent(engine.world, intent)[0]
    assert a.inventory.food == 2 and b.inventory.food == 1
    assert any(m.peer_id == a.id and "gave" in m.text for m in b.memories)
    assert engine.world.settlements[a.settlement_id].community.meals_given == 1
    b.position = Position(x=40, y=40)
    assert not resolve_intent(engine.world, intent)[0]
    assert a.inventory.food == 2 and b.inventory.food == 1


def test_public_board_is_local_and_completion_counts_actual_contributors(engine):
    w = engine.world
    a, b = list(w.agents.values())[:2]
    s = w.settlements[a.settlement_id]
    p = CommunityProject(
        id="farm-plan",
        kind="farm",
        target=Position(x=2, y=0),
        proposer_id=a.id,
        created_tick=0,
        deadline=100,
        cost={"wood": 2},
    )
    civic(s).projects = [p]
    a.position = s.center.model_copy()
    assert build_observation(w, a.id).settlement["community"]["projects"][0]["id"] == p.id
    a.position = Position(x=40, y=40)
    assert build_observation(w, a.id).settlement is None
    record_work(w, b, AgentIntent(actor_id=b.id, action=Action.STORE, item="wood", amount=2), True)
    assert p.contributors == {b.id: 1}
    record_work(w, a, AgentIntent(actor_id=a.id, action=Action.BUILD, target=p.target), False)
    assert a.id not in p.contributors
    w.buildings["farm-test"] = Building(
        id="farm-test", kind="farm", position=p.target, progress=100
    )
    assert update_projects(w, 5)[0][0] == "COMMUNITY_PROJECT_COMPLETED"
    assert p.status == "completed" and s.community.projects_completed == 1
    assert not update_projects(w, 6)


def test_repairs_consume_materials_and_do_not_resurrect_ruins(engine):
    w = engine.world
    a = next(iter(w.agents.values()))
    a.position = Position(x=0, y=0)
    a.inventory.wood = 2
    b = Building(
        id="damaged", kind="farm", position=Position(x=1, y=0), progress=100, durability=30
    )
    w.buildings[b.id] = b
    intent = AgentIntent(actor_id=a.id, action=Action.REPAIR, building_id=b.id)
    assert resolve_intent(w, intent)[0]
    assert b.durability == 50 and a.inventory.wood == 1
    b.durability = 0
    assert not resolve_intent(w, intent)[0]
    assert b.durability == 0 and a.inventory.wood == 1


def test_healthy_agent_can_choose_help_over_private_foraging(engine):
    w = engine.world
    a, b = list(w.agents.values())[:2]
    a.position, b.position = Position(x=0, y=0), Position(x=1, y=0)
    a.inventory.food, a.hunger, a.energy = 3, 10, 90
    b.inventory.food, b.hunger, b.health = 0, 85, 30
    o = build_observation(w, a.id, access=engine.access)
    intent = engine.policy.decide(o, preferred_goal="help_neighbor")
    assert intent.action == Action.GIVE and intent.peer_id == b.id
    a.hunger = 95
    intent = engine.policy.decide(
        build_observation(w, a.id, access=engine.access), preferred_goal="help_neighbor"
    )
    assert intent.action == Action.EAT


def test_old_settlement_serialization_and_new_community_replay(engine):
    import json

    s = next(iter(engine.world.settlements.values()))
    old = settlement_state(s)
    old.pop("community", None)
    assert settlement_state(Settlement.model_validate(old)) == old
    legacy_project = CommunityProject(
        id="legacy-project",
        kind="farm",
        target=s.center,
        proposer_id="agent-00",
        created_tick=0,
        deadline=100,
    ).model_dump(mode="json")
    legacy_project.pop("design")
    old["community"] = {
        "projects": [legacy_project],
        "contributions": {},
        "meals_given": 0,
        "repairs": 0,
        "projects_completed": 0,
    }
    assert settlement_state(Settlement.model_validate(old)) == old
    a, b = list(engine.world.agents.values())[:2]
    a.position, b.position = Position(x=0, y=0), Position(x=1, y=0)
    a.inventory.food, b.inventory.food = 3, 0
    initial = authoritative_state(engine.world)
    engine.store.connection.execute(
        "UPDATE snapshots SET state=?,state_hash=? WHERE run_id=?",
        (json.dumps(initial), state_hash(engine.world), engine.run_id),
    )
    engine.store.connection.commit()
    engine.tick([AgentIntent(actor_id=a.id, action=Action.GIVE, peer_id=b.id, item="food")])
    assert state_hash(engine.store.replay(engine.run_id)) == state_hash(engine.world)


def test_project_posting_validates_local_need_and_expires(engine):
    from app.simulation.policies.projects import propose_project

    a = next(iter(engine.world.agents.values()))
    s = engine.world.settlements[a.settlement_id]
    a.position = s.center.model_copy()
    s.storage.food = 0
    proposal = propose_project(build_observation(engine.world, a.id, access=engine.access))
    assert proposal is not None
    kind, target, _ = proposal
    intent = AgentIntent(
        actor_id=a.id, action=Action.PROPOSE_PROJECT, building_kind=kind, target=target
    )
    assert resolve_intent(engine.world, intent)[0]
    assert not resolve_intent(engine.world, intent)[0]
    p = s.community.projects[-1]
    assert update_projects(engine.world, p.deadline)[0][0] == "COMMUNITY_PROJECT_EXPIRED"
    assert p.status == "expired" and s.community.projects_completed == 0


def test_public_food_cannot_be_withdrawn_to_redeposit_without_need(engine):
    a = next(iter(engine.world.agents.values()))
    s = engine.world.settlements[a.settlement_id]
    a.position = s.center.model_copy()
    a.inventory.food, a.hunger, a.energy = 1, 10, 90
    s.storage.food = 4
    o = build_observation(engine.world, a.id, access=engine.access)
    intent = engine.policy.decide(o, preferred_goal="take_shared_food")
    candidate = next(c for c in intent.decision.candidates if c.goal == "take_shared_food")
    assert candidate.rejection
    a.inventory.food, a.hunger = 0, 55
    intent = engine.policy.decide(
        build_observation(engine.world, a.id, access=engine.access),
        preferred_goal="take_shared_food",
    )
    assert intent.action == Action.WITHDRAW


def test_shared_budget_does_not_withdraw_negative_personal_deficit(engine):
    a = next(iter(engine.world.agents.values()))
    s = engine.world.settlements[a.settlement_id]
    a.position = s.center.model_copy()
    a.inventory.wood, a.inventory.food, a.hunger, a.energy = 8, 2, 10, 90
    s.storage.wood, s.storage.seeds, s.storage.water = 1, 0, 0
    civic(s).projects = [
        CommunityProject(
            id="farm-budget",
            kind="farm",
            target=Position(x=2, y=0),
            proposer_id=a.id,
            created_tick=0,
            deadline=100,
            cost={"wood": 2, "seeds": 2, "water": 1},
        )
    ]
    intent = engine.policy.decide(
        build_observation(engine.world, a.id, access=engine.access), preferred_goal="take_materials"
    )
    assert intent.amount >= 1
    candidate = next(c for c in intent.decision.candidates if c.goal == "take_materials")
    assert candidate.rejection
