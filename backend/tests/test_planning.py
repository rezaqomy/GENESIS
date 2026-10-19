from app.simulation.cognition.tiers import action_snapshot
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import agent_state, state_hash
from app.simulation.models.domain import (
    Action,
    Agent,
    AgentIntent,
    Building,
    CandidateGoal,
    Position,
    TaskPlan,
    Terrain,
    Tile,
    WorldConfig,
)
from app.simulation.observation.builder import Observation, build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.planning.navigation import coordinate_movements
from app.simulation.planning.tasks import finish_task, select_task, skill_bonus, update_task
from app.simulation.policies.utility import UtilityPolicy


def actor(aid="agent-00", x=0, y=0):
    return Agent(id=aid, name=aid, age=25, visual_color="#fff", position=Position(x=x, y=y))


def task(a, kind="forage", stage="acquire", **kwargs):
    return TaskPlan(
        **(
            dict(
                id=f"{a.id}:0:{kind}",
                kind=kind,
                context="day:safe",
                stage=stage,
                started_tick=0,
                last_progress_tick=0,
                deadline=120,
                origin=a.position.model_copy(),
                initial_food=a.inventory.food,
                initial_hunger=a.hunger,
            )
            | kwargs
        )
    )


def observation(a, occupied=None):
    return Observation(
        seed=42,
        tick=1,
        self_agent=a,
        environment={"night": False},
        path_budget=2000,
        tiles=[
            Tile(position=Position(x=x, y=y), terrain=Terrain.GRASS, walkable=True)
            for x in range(-4, 5)
            for y in range(-4, 5)
        ],
        resources=[],
        occupied=occupied or [],
    )


def test_task_persists_through_goals_and_uses_actual_food_completion():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    a = engine.world.agents["agent-00"]
    a.inventory.food, a.hunger = 0, 60
    a.task = task(a)
    o = build_observation(engine.world, a.id, access=engine.access)
    intent = engine.policy.decide(o)
    assert intent.task.id == a.task.id
    assert intent.decision.selected_goal in ("find_food", "take_shared_food")
    a.inventory.food = 2
    o = build_observation(engine.world, a.id, access=engine.access)
    assert engine.policy.decide(o).decision.selected_goal == "eat"
    # A final food acquisition, with low hunger, verifies the whole task.
    before = action_snapshot(a)
    a.hunger, a.inventory.food = 35, 2
    result = update_task(
        engine.world, a, AgentIntent(actor_id=a.id, action=Action.GATHER), True, before, 4
    )
    assert result.status == "succeeded" and result.hunger_delta < 0
    assert a.skills["forage:day:safe"].successes == 1
    store.close()


def test_expedition_prepares_food_then_energy_then_explores_and_returns():
    a = actor()
    a.task = task(a, "expedition", "provision")
    a.inventory.food, a.energy = 0, 50
    o = observation(a)
    names = ["find_food", "rest", "explore", "return_home"]
    valid = [CandidateGoal(goal=g, utility=0.5) for g in names]
    plans = {g: (Action.MOVE, {"destination": Position(x=20, y=0)}) for g in names}
    p, g = select_task(o, "explore", valid, plans)
    assert (p.stage, g) == ("provision", "find_food")
    a.task, a.inventory.food = p, 2
    p, g = select_task(o, "explore", valid, plans)
    assert (p.stage, g) == ("recover", "rest")
    a.task, a.energy = p, 80
    p, g = select_task(o, "explore", valid, plans)
    assert (p.stage, g) == ("explore", "explore")
    p.exploration_moves, p.max_home_distance = 40, 20
    a.task = p
    p, g = select_task(o, "explore", valid, plans)
    assert (p.stage, g) == ("return", "return_home")
    # More supplies do not undo a return decision.
    a.task = p
    assert select_task(o, "explore", valid, plans)[0].stage == "return"


def test_emergency_overrides_task_and_low_energy_recovers():
    a = actor()
    a.task = task(a, "expedition", "explore")
    a.hunger, a.inventory.food, a.energy = 95, 1, 5
    o = observation(a)
    intent = UtilityPolicy().decide(o, preferred_goal="explore")
    assert intent.action == Action.EAT
    a.hunger = 20
    assert UtilityPolicy().decide(o, preferred_goal="explore").action == Action.REST


def test_failed_first_attempt_not_verified_and_timeout_ignores_idle_acceptance():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store)
    a = engine.world.agents["agent-00"]
    a.task = task(a)
    result = update_task(
        engine.world,
        a,
        AgentIntent(actor_id=a.id, action=Action.IDLE),
        True,
        action_snapshot(a),
        25,
    )
    assert result.status == "failed"
    assert not a.skills and len(a.task_history) == 1
    assert finish_task(a, "failed", "duplicate", 26) is None
    assert len(a.task_history) == 1
    store.close()


def test_skill_uses_verified_successes_context_and_later_failure():
    a = actor()
    a.task = task(a)
    finish_task(a, "succeeded", "Food reserve replenished", 5)
    assert skill_bonus(a, "find_food", 6, {"night": False}) > 0
    assert skill_bonus(a, "find_food", 6, {"night": True}) == 0
    previous = skill_bonus(a, "find_food", 6, {"night": False})
    a.task = task(a)
    finish_task(a, "failed", "No progress", 6)
    assert a.skills["forage:day:safe"].failures == 1
    assert skill_bonus(a, "find_food", 6, {"night": False}) < previous


def test_other_builder_completion_is_not_claimed_as_a_skill():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store)
    a = engine.world.agents["agent-00"]
    target = Position(x=50, y=50)
    a.position = Position(x=50, y=49)  # The completed site must be observed locally.
    a.task = task(a, "construction", "build", target=target, building_kind="shelter")
    engine.world.buildings["peer-building"] = Building(
        id="peer-building", kind="shelter", position=target, progress=100
    )
    result = update_task(
        engine.world, a, AgentIntent(actor_id=a.id, action=Action.IDLE), True, action_snapshot(a), 1
    )
    assert result.status == "cancelled" and not a.skills
    store.close()


def test_reservations_yield_and_rotate_without_mutating_observations_or_intents():
    a, b = actor(), actor("agent-01", 2, 0)
    observations = [observation(a, [b.position]), observation(b, [a.position])]
    # A one-cell corridor admits only one actor to the contested tile.
    for o in observations:
        o.tiles = [t for t in o.tiles if t.position.y == 0 and 0 <= t.position.x <= 2]
    intents = [
        AgentIntent(
            actor_id=p.id,
            action=Action.MOVE,
            target=Position(x=1, y=0),
            destination=Position(x=1, y=0),
        )
        for p in (a, b)
    ]
    before = [i.model_dump_json() for i in intents]
    result = coordinate_movements(observations, intents, 0)
    assert [i.action for i in result] == [Action.MOVE, Action.IDLE]
    assert result[1].navigation_note and result[1].target is None
    rotated = coordinate_movements(observations, intents, 1)
    assert [i.action for i in rotated] == [Action.IDLE, Action.MOVE]
    assert before == [i.model_dump_json() for i in intents]


def test_reservations_find_a_local_detour():
    a, b = actor(), actor("agent-01", 2, 0)
    observations = [observation(a, [b.position]), observation(b, [a.position])]
    intents = [
        AgentIntent(
            actor_id=p.id,
            action=Action.MOVE,
            target=Position(x=1, y=0),
            destination=Position(x=1, y=3),
        )
        for p in (a, b)
    ]
    result = coordinate_movements(observations, intents, 0)
    assert all(i.action == Action.MOVE for i in result)
    assert result[0].target != result[1].target
    assert result[1].navigation_note.startswith("Replanned")
    assert all(p.position.distance(i.target) == 1 for p, i in zip((a, b), result, strict=True))


def test_task_energy_cost_counts_travel_not_just_terminal_action():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store)
    a = engine.world.agents["agent-00"]
    a.task = task(a, target=Position(x=10, y=0))
    before = action_snapshot(a)
    a.energy -= 2
    a.position = Position(x=a.position.x + 1, y=a.position.y)
    update_task(engine.world, a, AgentIntent(actor_id=a.id, action=Action.MOVE), True, before, 1)
    assert a.task.energy_spent == 2
    assert a.task.actions == 1
    store.close()


def test_construction_material_acquisition_counts_as_progress():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True), store)
    a = engine.world.agents["agent-00"]
    a.task = task(a, "construction", "materials", building_kind="shelter")
    before = action_snapshot(a)
    a.inventory.wood += 1
    result = update_task(
        engine.world, a, AgentIntent(actor_id=a.id, action=Action.GATHER), True, before, 24
    )
    assert result is None and a.task.last_progress_tick == 24
    # Unrelated food does not hide a stalled construction plan.
    before = action_snapshot(a)
    a.inventory.food += 1
    result = update_task(
        engine.world, a, AgentIntent(actor_id=a.id, action=Action.GATHER), True, before, 48
    )
    assert result.status == "failed"
    store.close()


def test_plans_history_skills_and_navigation_replay_restart(tmp_path):
    path = str(tmp_path / "plans.sqlite")
    store = EventStore(path)
    engine = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    for _ in range(35):
        engine.tick()
    assert any(a.task_history for a in engine.world.agents.values())
    assert any(a.skills for a in engine.world.agents.values())
    expected = state_hash(engine.world)
    assert state_hash(store.replay(engine.run_id)) == expected
    assert state_hash(store.replay(engine.run_id, use_snapshot=True)) == expected
    store.close()
    store = EventStore(path)
    restored = Engine(WorldConfig(infinite=True), store, UtilityPolicy(), restore=True)
    assert state_hash(restored.world) == expected
    restored.reset(WorldConfig(infinite=True))
    assert all(
        a.task is None and not a.skills and not a.task_history
        for a in restored.world.agents.values()
    )
    store.close()


def test_old_agent_record_keeps_absent_task_fields_absent():
    a = actor()
    data = agent_state(a)
    assert all(k not in data for k in ("task", "task_history", "skills"))
    assert agent_state(Agent.model_validate(data)) == data
