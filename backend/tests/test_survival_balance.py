"""Survival should create recoverable journeys, not sudden deaths or cargo deadlocks."""

from app.simulation.actions.provisions import carrying_room
from app.simulation.actions.resolver import advance_physiology, resolve_intent, resolve_survival
from app.simulation.chunks.access import WorldAccess
from app.simulation.engine.core import Engine
from app.simulation.engine.generation import generate_world
from app.simulation.events.reducer import authoritative_state, state_hash
from app.simulation.models.domain import (
    Action,
    AgentIntent,
    Building,
    Inventory,
    Position,
    WorldConfig,
)
from app.simulation.observation.builder import build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


def test_no_food_allows_days_for_rescue_but_is_eventually_fatal():
    w = generate_world(WorldConfig(infinite=True, agent_count=1))
    a = w.agents["agent-00"]
    a.hunger = 0
    for tick in range(4 * 240):
        w.tick = tick
        advance_physiology(w)
        resolve_survival(w)
    assert a.alive and a.health >= 70
    for tick in range(4 * 240, 8 * 240):
        w.tick = tick
        advance_physiology(w)
        resolve_survival(w)
    assert not a.alive and a.health == 0


def test_one_day_needs_less_than_one_meal_and_no_starvation_damage():
    w = generate_world(WorldConfig(infinite=True, agent_count=1))
    a = w.agents["agent-00"]
    a.hunger = 20
    for tick in range(240):
        w.tick = tick
        advance_physiology(w)
        resolve_survival(w)
    assert a.hunger == 50 and a.health == 100 and a.alive


def test_last_minute_meal_precedes_damage_and_replay_matches():
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True, agent_count=1), store)
    a = e.world.agents["agent-00"]
    a.position = Position(x=0, y=0)  # Warm camp excludes unrelated cold damage.
    a.hunger, a.health, a.inventory.food = 100, 1, 1
    e.world.tick = 7
    store.append([e.event("WORLD_CREATED", {"state": authoritative_state(e.world)})], e.world)
    e.tick([AgentIntent(actor_id=a.id, action=Action.EAT)])
    assert a.alive and a.health == 1 and a.hunger == 65 and a.inventory.food == 0
    assert state_hash(e.world) == state_hash(store.replay(e.run_id))
    store.close()


def test_old_full_backpack_can_be_cleared_then_collect_food():
    w = generate_world(WorldConfig(infinite=True, agent_count=1))
    a = w.agents["agent-00"]
    a.position = Position(x=4, y=-4)
    a.inventory = Inventory(wood=21, tools={"axe": 50, "pickaxe": 50, "torch": 50}, capacity=24)
    a.hunger = 95
    access = WorldAccess(w)
    intent = UtilityPolicy().decide(build_observation(w, a.id, access=access))
    assert intent.action == Action.DISCARD and intent.item == "wood" and intent.amount == 3
    assert resolve_intent(w, intent, access)[0]
    assert carrying_room(a.inventory, "food") == 3
    gather = AgentIntent(actor_id=a.id, action=Action.GATHER, resource_id="r:4:-4:food")
    assert resolve_intent(w, gather, access)[0]
    assert a.inventory.food == 1
    assert UtilityPolicy().decide(build_observation(w, a.id, access=access)).action == Action.EAT
    assert not resolve_intent(
        w, AgentIntent(actor_id=a.id, action=Action.DISCARD, item="food"), access
    )[0]


def test_bulk_materials_cannot_block_personal_or_shared_provisions():
    assert carrying_room(Inventory(wood=21, capacity=24), "wood") == 0
    assert carrying_room(Inventory(wood=21, capacity=24), "food") == 3
    shared = Inventory(wood=68, capacity=80)
    assert carrying_room(shared, "wood", communal=True) == 0
    assert carrying_room(shared, "water", communal=True) == 12


def test_real_water_trip_continues_outside_settlement_sight_and_returns():
    w = generate_world(WorldConfig(infinite=True, agent_count=1))
    a = w.agents["agent-00"]
    w.buildings["farm"] = Building(
        id="farm",
        kind="farm",
        position=Position(x=6, y=5),
        settlement_id=a.settlement_id,
        progress=100,
    )
    w.settlements[a.settlement_id].buildings.append("farm")
    w.settlements[a.settlement_id].storage.water = 0
    a.position, a.hunger = Position(x=7, y=-1), 10
    a.inventory.food = 3
    a.personality.cooperation = 1
    access = WorldAccess(w)
    went_out_of_sight = False
    for tick in range(70):
        w.tick = tick
        o = build_observation(w, a.id, access=access)
        intent = UtilityPolicy().decide(o)
        went_out_of_sight |= o.settlement is None
        assert intent.decision.selected_goal in ("supply_farm", "rest")
        assert resolve_intent(w, intent, access)[0]
        a.decision = intent.decision
        if w.settlements[a.settlement_id].storage.water:
            break
    assert went_out_of_sight and w.settlements[a.settlement_id].storage.water > 0
