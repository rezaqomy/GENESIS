import pytest

from app.simulation.actions.resolver import resolve_intent
from app.simulation.chunks.generator import terrain_at
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import (
    Action,
    AgentIntent,
    Building,
    DesignTrial,
    HousingKnowledge,
    Position,
    ShelterDesign,
    Terrain,
    WorldConfig,
)
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy
from app.simulation.settlements.effects import local_effects


def grant_tested_design(agent):
    # Payment/migration fixtures already know a design; novice learning is tested separately.
    agent.housing = HousingKnowledge(
        trials=[DesignTrial(design=ShelterDesign(), tick=0, score=0.3, stood=True)]
    )


@pytest.fixture
def settlement_engine():
    s = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), s, UtilityPolicy())
    yield e
    s.close()


def test_viable_group_spawn(settlement_engine):
    e = settlement_engine
    positions = [(a.position.x, a.position.y) for a in e.world.agents.values()]
    assert len(set(positions)) == 10
    assert all(abs(x) <= 3 and abs(y) <= 3 for x, y in positions)
    assert all(e.access.tile(a.position).walkable for a in e.world.agents.values())
    assert terrain_at(42, 10, 0) == Terrain.WATER
    assert {r.kind for _, r in e.access.cache.get(0, 0).resources.items()} >= {
        "food",
        "wood",
        "seeds",
    }
    assert e.world.buildings["building-0"].kind == "campfire"


def test_storage_transfers_and_capacity(settlement_engine):
    e = settlement_engine
    a = next(iter(e.world.agents.values()))
    a.position = Position(x=0, y=1)
    shared = e.world.settlements[a.settlement_id].storage
    before = shared.food
    assert resolve_intent(
        e.world, AgentIntent(actor_id=a.id, action=Action.WITHDRAW, item="food"), e.access
    )[0]
    assert a.inventory.food == 1 and shared.food == before - 1
    a.inventory.wood = 4
    assert resolve_intent(
        e.world, AgentIntent(actor_id=a.id, action=Action.STORE, item="wood", amount=4), e.access
    )[0]
    assert a.inventory.wood == 0
    a.position = Position(x=40, y=40)
    assert not resolve_intent(
        e.world, AgentIntent(actor_id=a.id, action=Action.WITHDRAW, item="food"), e.access
    )[0]


def test_build_cost_progress_shelter_and_replay(settlement_engine):
    e = settlement_engine
    a = next(iter(e.world.agents.values()))
    grant_tested_design(a)
    a.position = Position(x=2, y=1)
    s = e.world.settlements[a.settlement_id]
    wood = s.storage.wood
    intent = AgentIntent(
        actor_id=a.id, action=Action.BUILD, target=Position(x=2, y=2), building_kind="shelter"
    )
    for _ in range(4):
        e.tick([intent])
    b = e.world.buildings["building:2:2"]
    assert b.progress == 100 and s.storage.wood == wood - 6
    a.energy = 10
    e.tick([AgentIntent(actor_id=a.id, action=Action.REST)])
    assert a.energy > 23
    assert 0 < local_effects(e.world, a.position)["comfort"] < 0.7
    assert state_hash(e.store.replay(e.run_id)) == state_hash(e.world)
    assert not resolve_intent(e.world, intent, e.access)[0]


def test_fire_fuel_local_safety_and_visibility(settlement_engine):
    e = settlement_engine
    w = e.world
    fire = w.buildings["building-0"]
    lit = local_effects(w, Position(x=1, y=0))
    far = local_effects(w, Position(x=40, y=0))
    assert lit["warmth"] > far["warmth"] and lit["safety"] > far["safety"]
    fuel = fire.fuel
    for _ in range(12):
        e.tick([])
    assert fire.fuel == fuel - 1
    fire.fuel = 0
    assert local_effects(w, Position(x=1, y=0))["warmth"] == 0
    w.buildings["tower"] = Building(
        id="tower", kind="watchtower", position=Position(x=40, y=0), progress=100
    )
    assert local_effects(w, Position(x=40, y=1))["visibility"] == 12
    assert local_effects(w, Position(x=60, y=0))["visibility"] == 8


def test_bridge_road_wall_tool_and_farm_effects(settlement_engine):
    e = settlement_engine
    w = e.world
    a = next(iter(w.agents.values()))
    # Completed structures are fixtures for testing their effects, not policy outcomes.
    w.buildings["bridge"] = Building(
        id="bridge", kind="bridge", position=Position(x=10, y=0), progress=100
    )
    assert e.access.tile(Position(x=10, y=0)).walkable
    w.buildings["wall"] = Building(
        id="wall", kind="wooden_wall", position=Position(x=6, y=0), progress=100
    )
    assert not e.access.tile(Position(x=6, y=0)).walkable
    a.position = Position(x=1, y=1)
    w.buildings["road"] = Building(
        id="road", kind="road", position=Position(x=0, y=1), progress=100
    )
    energy = a.energy
    assert resolve_intent(
        w, AgentIntent(actor_id=a.id, action=Action.MOVE, target=Position(x=0, y=1)), e.access
    )[0]
    assert a.energy == energy - 1
    a.position = Position(x=-5, y=-2)
    a.inventory.tools["axe"] = 5
    assert resolve_intent(
        w, AgentIntent(actor_id=a.id, action=Action.GATHER, resource_id="r:-5:-3:wood"), e.access
    )[0]
    assert a.inventory.wood == 2 and a.inventory.tools["axe"] == 4
    s = w.settlements[a.settlement_id]
    w.buildings["farm"] = Building(
        id="farm", kind="farm", position=Position(x=6, y=5), progress=100, settlement_id=s.id
    )
    initial = s.storage.food
    for _ in range(24):
        e.tick([])
    assert s.storage.food == initial + 2 and w.buildings["farm"].food == 2


def test_autonomous_construction_and_deterministic_replay(settlement_engine):
    e = settlement_engine
    actions = set()
    for _ in range(80):
        for ev in e.tick():
            if ev.event_type == "ACTION_RESOLVED":
                actions.add(ev.payload["action"])
    assert "BUILD" in actions and "GATHER" in actions
    # Food production may precede housing when the community reserve falls.
    assert any(
        b.kind in ("shelter", "farm") and b.progress == 100 for b in e.world.buildings.values()
    )
    assert state_hash(e.world) == state_hash(e.store.replay(e.run_id))
    assert state_hash(e.world) == state_hash(e.store.replay(e.run_id, use_snapshot=True))


def test_crafting_refueling_and_conditional_migration(settlement_engine):
    e = settlement_engine
    w = e.world
    a = w.agents["agent-00"]
    grant_tested_design(a)
    a.position = Position(x=-2, y=-1)
    w.buildings["bench"] = Building(
        id="bench", kind="workbench", position=Position(x=-3, y=-1), progress=100
    )
    from app.simulation.engineering.invention import design_id
    from app.simulation.models.domain import ToolDesign

    assert not resolve_intent(
        w, AgentIntent(actor_id=a.id, action=Action.CRAFT, item="axe"), e.access
    )[0]
    design = ToolDesign(core="stone", grip="wood", binding="fiber", form="edge", length=2)
    for _ in range(3):
        assert resolve_intent(
            w,
            AgentIntent(actor_id=a.id, action=Action.EXPERIMENT_TOOL, tool_design=design),
            e.access,
        )[0]
    key = design_id(design)
    a.inventory.tools[key] = 0
    assert resolve_intent(
        w, AgentIntent(actor_id=a.id, action=Action.CRAFT, item=key, tool_design=design), e.access
    )[0]
    assert a.inventory.tools[key] > 0
    assert not resolve_intent(
        w, AgentIntent(actor_id=a.id, action=Action.CRAFT, item=key, tool_design=design), e.access
    )[0]
    a.position = Position(x=0, y=1)
    fire = w.buildings["building-0"]
    fuel = fire.fuel
    assert resolve_intent(
        w, AgentIntent(actor_id=a.id, action=Action.REFUEL, building_id=fire.id), e.access
    )[0]
    assert fire.fuel == fuel + 4
    a.position = Position(x=35, y=0)
    from app.simulation.models.domain import Tile

    w.terrain_modifications["35,0"] = Tile(
        position=a.position, terrain=Terrain.GRASS, walkable=True
    )
    a.personality.independence = 1
    a.personality.loyalty = 0
    a.time_away = 150
    a.inventory.wood = 3
    a.inventory.fiber = 2
    intent = AgentIntent(
        actor_id=a.id, action=Action.BUILD, target=a.position, building_kind="remote_camp"
    )
    for _ in range(4):
        assert resolve_intent(w, intent, e.access)[0]
    assert a.lifestyle == "wanderer" and a.settlement_id is None
    assert a.id not in w.settlements["settlement-0"].members
    assert a.home == Position(x=35, y=0)


def test_torch_effect_and_night_durability(settlement_engine):
    e = settlement_engine
    a = e.world.agents["agent-00"]
    a.position = Position(x=40, y=0)
    unlit = local_effects(e.world, a.position)
    a.inventory.tools["torch"] = 80
    lit = local_effects(e.world, a.position)
    assert lit["safety"] > unlit["safety"]
    assert lit["warmth"] > unlit["warmth"]
    for _ in range(12):
        e.tick([])
    assert a.inventory.tools["torch"] == 79
    assert state_hash(e.world) == state_hash(e.store.replay(e.run_id))


def test_distant_project_hauling_reserves_materials(settlement_engine):
    from app.simulation.observation.builder import build_observation

    e = settlement_engine
    a = e.world.agents["agent-00"]
    a.position = Position(x=0, y=1)
    a.hunger = 0
    a.energy = 100
    a.inventory.food = 2
    a.personality.ambition = 1
    a.personality.cooperation = 1
    a.personality.curiosity = 0
    a.personality.exploration_drive = 0
    a.personality.comfort_preference = 1
    s = e.world.settlements[a.settlement_id]
    # A locally observed unfinished farm replaces the old hard-coded, unseen farm site.
    s.storage.food = 0
    e.world.buildings["hauling-farm"] = Building(
        id="hauling-farm",
        kind="farm",
        position=Position(x=3, y=6),
        progress=0,
        durability=0,
        settlement_id=s.id,
    )
    for i, kind in enumerate(("shelter", "shelter", "storage", "workbench")):
        b = Building(
            id=f"fixture-{i}",
            kind=kind,
            position=Position(x=-3, y=i - 3),
            progress=100,
            settlement_id=s.id,
        )
        e.world.buildings[b.id] = b
        s.buildings.append(b.id)
    decision = e.policy.decide(build_observation(e.world, a.id, access=e.access)).decision
    assert next(c for c in decision.candidates if c.goal == "take_materials").rejection is None
    a.inventory.wood = 2
    a.inventory.seeds = 2
    a.inventory.water = 1
    intent = e.policy.decide(build_observation(e.world, a.id, access=e.access))
    assert intent.decision.selected_goal == "improve_settlement"
    assert next(c for c in intent.decision.candidates if c.goal == "store_resources").rejection
    assert intent.action == Action.MOVE


def test_policy_completes_paid_remote_camp_without_second_material_charge(settlement_engine):
    from app.simulation.models.domain import Tile
    from app.simulation.observation.builder import build_observation

    e = settlement_engine
    a = e.world.agents["agent-00"]
    grant_tested_design(a)
    a.position = Position(x=35, y=0)
    e.world.terrain_modifications["35,0"] = Tile(
        position=a.position, terrain=Terrain.GRASS, walkable=True
    )
    a.energy = 60
    a.hunger = 10
    a.inventory.food = 3
    a.personality.independence = 1
    a.personality.loyalty = 0
    a.personality.curiosity = 0
    a.personality.exploration_drive = 0
    a.personality.risk_tolerance = 1
    a.psychology.sense_of_safety = 0.2
    e.world.buildings["pending-camp"] = Building(
        id="pending-camp", kind="remote_camp", position=a.position, owner_id=a.id, progress=25
    )
    intent = e.policy.decide(build_observation(e.world, a.id, access=e.access))
    assert intent.decision.selected_goal == "establish_camp"
    assert intent.action == Action.BUILD
    assert resolve_intent(e.world, intent, e.access)[0]
    assert e.world.buildings["pending-camp"].progress == 50
    assert a.inventory.wood == 0 and a.inventory.fiber == 0
