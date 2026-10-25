import json

import pytest

from app.simulation.actions.resolver import resolve_intent
from app.simulation.ecology.environment import advance_ecology, living, release_dead
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import authoritative_state, state_hash
from app.simulation.models.domain import (
    Action,
    AgentIntent,
    Animal,
    CombatState,
    Crop,
    DroppedItems,
    Inventory,
    Position,
    Terrain,
    Tile,
    WorldConfig,
)
from app.simulation.observation.builder import build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


@pytest.fixture
def scene():
    store = EventStore(":memory:")
    engine = Engine(WorldConfig(infinite=True, agent_count=3), store, UtilityPolicy())
    w = engine.world
    a, b, c = w.agents.values()
    for i, agent in enumerate((a, b, c)):
        agent.position = Position(x=100 + i, y=100)
        agent.home = Position(x=100, y=100)
        agent.energy, agent.hunger = 100, 10
        agent.inventory = Inventory(capacity=20)
    # Pick a naturally empty plot, with a controlled local source of irrigation.
    p = next(
        Position(x=x, y=101)
        for x in range(100, 180)
        if not engine.access.visible_resources(Position(x=x, y=101), 0)
    )
    a.position = Position(x=p.x, y=100)
    b.position = Position(x=p.x + 1, y=100)
    c.position = Position(x=p.x + 2, y=100)
    a.home = p.model_copy()
    for x in range(p.x - 2, p.x + 4):
        for y in range(98, 104):
            v = Position(x=x, y=y)
            w.terrain_modifications[f"{x},{y}"] = Tile(
                position=v, terrain=Terrain.GRASS, walkable=True
            )
    living(w)
    yield engine, a, b, c, p
    store.close()


def act(e, a, action, **kwargs):
    return resolve_intent(e.world, AgentIntent(actor_id=a.id, action=action, **kwargs), e.access)


def test_crop_needs_seed_soil_time_and_harvest_room(scene):
    e, a, _, _, p = scene
    assert not act(e, a, Action.PLANT, target=p)[0]
    assert act(e, a, Action.TILL, target=p)[0]
    assert not act(e, a, Action.PLANT, target=p)[0]
    a.inventory.seeds = 1
    assert act(e, a, Action.PLANT, target=p)[0]
    assert a.inventory.seeds == 0
    crop = next(iter(e.world.ecosystem.crops.values()))
    assert not act(e, a, Action.HARVEST, target=p)[0]
    for tick in range(8, 641, 8):
        advance_ecology(e.world, e.access, tick, {"weather": "rain", "night": False})
    assert crop.growth == 80
    a.energy = 100
    a.inventory.wood = 16
    assert not act(e, a, Action.HARVEST, target=p)[0]
    a.inventory.wood = 0
    assert act(e, a, Action.HARVEST, target=p)[0]
    assert (a.inventory.food, a.inventory.seeds) == (3, 2)
    assert not act(e, a, Action.HARVEST, target=p)[0]


def test_drought_night_water_and_dead_crops(scene):
    e, a, _, _, p = scene
    # Make irrigation impossible in this fixture.
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0), (0, 2), (0, -2), (2, 0), (-2, 0)):
        v = Position(x=p.x + dx, y=p.y + dy)
        e.world.terrain_modifications[f"{v.x},{v.y}"] = Tile(
            position=v, terrain=Terrain.GRASS, walkable=True
        )
    crop = Crop(id="crop", position=p, owner_id=a.id, planted_tick=0, moisture=0, health=2)
    e.world.ecosystem.crops[f"crop:{p.x},{p.y}"] = crop
    advance_ecology(e.world, e.access, 8, {"weather": "clear", "night": True})
    assert crop.health == 0 and crop.growth == 0
    assert act(e, a, Action.HARVEST, target=p)[0]
    assert a.inventory.total == 0
    crop = Crop(id="crop", position=p, owner_id=a.id, planted_tick=0, moisture=10)
    e.world.ecosystem.crops[f"crop:{p.x},{p.y}"] = crop
    assert not act(e, a, Action.WATER_CROP, target=p)[0]
    a.inventory.water = 1
    assert act(e, a, Action.WATER_CROP, target=p)[0]
    assert crop.moisture == 50 and a.inventory.water == 0
    advance_ecology(e.world, e.access, 16, {"weather": "clear", "night": True})
    assert crop.growth == 0


def test_tilling_cannot_make_an_infinite_clay_loop(scene):
    e, a, _, _, p = scene
    assert act(e, a, Action.TILL, target=p)[0]
    assert act(e, a, Action.DIG, target=p)[0]
    assert a.inventory.clay == 1
    assert not act(e, a, Action.TILL, target=p)[0]


def test_plant_blocks_earthwork_and_building(scene):
    e, a, _, _, p = scene
    a.inventory.seeds = 1
    assert act(e, a, Action.TILL, target=p)[0]
    assert act(e, a, Action.PLANT, target=p)[0]
    assert not act(e, a, Action.DIG, target=p)[0]
    assert not act(e, a, Action.BUILD, target=p, building_kind="campfire")[0]


def add_animal(e, p, **kw):
    animal = Animal(id=kw.pop("id", "test-animal"), species="cow", position=p, born_tick=-240, **kw)
    e.world.ecosystem.animals[animal.id] = animal
    return animal


def test_feeding_costs_seeds_and_trust_belongs_to_one_tamer(scene):
    e, a, b, _, p = scene
    animal = add_animal(e, p)
    assert not act(e, a, Action.FEED, entity_id=animal.id)[0]
    a.inventory.seeds, b.inventory.seeds = 4, 1
    assert act(e, a, Action.FEED, entity_id=animal.id)[0]
    assert animal.trust == 1 and animal.owner_id is None
    assert not act(e, a, Action.FEED, entity_id=animal.id)[0]
    animal.hunger = 20
    b.position = a.position.model_copy()
    assert act(e, b, Action.FEED, entity_id=animal.id)[0]
    assert animal.trust == 1 and animal.tamer_id == b.id
    for _ in range(3):
        animal.hunger = 20
        assert act(e, a, Action.FEED, entity_id=animal.id)[0]
    assert animal.trust == 3 and animal.owner_id == a.id
    b.inventory.seeds = 1
    assert not act(e, b, Action.FEED, entity_id=animal.id)[0]


def test_breeding_requires_two_fed_tame_adults_and_has_cooldown(scene):
    e, a, _, _, p = scene
    x = add_animal(e, p, owner_id=a.id, trust=3)
    y = add_animal(e, p, id="mate", owner_id=a.id, trust=3)
    assert not act(e, a, Action.BREED, entity_id=x.id, resource_id=y.id)[0]
    x.ready_until = y.ready_until = 120
    assert act(e, a, Action.BREED, entity_id=x.id, resource_id=y.id)[0]
    child = next(v for v in e.world.ecosystem.animals.values() if v.id.startswith("offspring:"))
    assert child.born_tick == 1 and child.owner_id == a.id
    assert not act(e, a, Action.BREED, entity_id=x.id, resource_id=y.id)[0]
    assert not act(e, a, Action.COLLECT, entity_id=child.id)[0]
    assert act(e, a, Action.COLLECT, entity_id=x.id)[0]
    assert not act(e, a, Action.COLLECT, entity_id=x.id)[0]
    assert a.inventory.food == 1


def test_attack_range_cooldown_wear_death_and_drop_conservation(scene):
    e, a, b, _, _ = scene
    b.health = 14
    b.inventory = Inventory(food=2, products={"metal": 1}, tools={"pickaxe": 7}, capacity=20)
    a.inventory.tools["axe"] = 2
    assert act(e, a, Action.ATTACK, peer_id=b.id)[0]
    assert not b.alive and b.combat.death_cause == f"killed by {a.name}"
    release_dead(e.world, 1)
    assert b.inventory.total == 0
    drop = e.world.ecosystem.drops[f"grave:{b.id}"]
    assert drop.inventory.total == 4 and drop.inventory.tools["pickaxe"] == 7
    assert a.inventory.tools["axe"] == 1
    release_dead(e.world, 2)
    assert len(e.world.ecosystem.drops) == 1
    assert act(e, a, Action.PICK_UP, entity_id=drop.id, item="pickaxe")[0]
    assert a.inventory.tools["pickaxe"] == 7
    assert not act(e, a, Action.PICK_UP, entity_id=drop.id, item="pickaxe")[0]
    assert act(e, a, Action.PICK_UP, entity_id=drop.id, item="metal")[0]
    assert a.inventory.products["metal"] == 1


def test_combat_validation_and_victim_response(scene):
    e, a, b, _, _ = scene
    assert act(e, a, Action.ATTACK, peer_id=b.id)[0]
    health = b.health
    assert not act(e, a, Action.ATTACK, peer_id=b.id)[0]
    assert b.health == health
    intent = e.policy.decide(build_observation(e.world, b.id, access=e.access))
    assert intent.decision.selected_goal == "defend_self" and intent.peer_id == a.id
    b.health = 10
    intent = e.policy.decide(build_observation(e.world, b.id, access=e.access))
    assert intent.decision.selected_goal == "flee_attack" and intent.action == Action.MOVE
    a.position = Position(x=-100, y=-100)
    e.world.tick = 8
    assert not act(e, a, Action.ATTACK, peer_id=b.id)[0]


def test_theft_transfers_real_stock_and_harms_relationships(scene):
    e, a, b, witness, _ = scene
    b.inventory.food = 2
    assert act(e, a, Action.STEAL, peer_id=b.id, item="food", amount=2)[0]
    assert a.inventory.food == 2 and b.inventory.food == 0
    assert b.relationships[a.id] < 0 and witness.relationships[a.id] < 0
    assert b.memories[-1].peer_id == a.id
    assert not act(e, a, Action.STEAL, peer_id=b.id, item="food")[0]
    assert not act(e, a, Action.STEAL, peer_id=b.id, item="capacity")[0]
    from app.simulation.settlements.environment import experience_tick

    experience_tick(e.world, e.access)
    assert b.relationships[a.id] < 0 and witness.relationships[a.id] < 0


def test_pickup_rejects_metadata_and_full_inventory(scene):
    e, a, _, _, p = scene
    drop = DroppedItems(id="drop", position=p, inventory=Inventory(food=2), expires=20)
    e.world.ecosystem.drops[drop.id] = drop
    assert not act(e, a, Action.PICK_UP, entity_id=drop.id, item="capacity")[0]
    a.inventory.wood = a.inventory.capacity
    assert not act(e, a, Action.PICK_UP, entity_id=drop.id, item="food")[0]
    assert drop.inventory.food == 2
    a.inventory.wood = 0
    assert act(e, a, Action.PICK_UP, entity_id=drop.id, item="food", amount=2)[0]
    assert not e.world.ecosystem.drops


def test_ecosystem_actions_cannot_smuggle_dialogue(scene):
    e, a, b, _, p = scene
    animal = add_animal(e, p)
    a.inventory.seeds = 1
    assert not act(e, a, Action.FEED, entity_id=animal.id, utterance="hello", peer_id=b.id)[0]
    assert a.inventory.seeds == 1 and animal.trust == 0


def test_dropped_supplies_decay_without_restocking_animals(scene):
    e, a, _, _, p = scene
    e.world.ecosystem.drops["old"] = DroppedItems(
        id="old", position=p, inventory=Inventory(food=2), expires=1
    )
    advance_ecology(e.world, e.access, 24, {"weather": "clear", "night": False})
    assert "old" not in e.world.ecosystem.drops
    visited = list(e.world.ecosystem.habitats)
    e.world.ecosystem.animals.clear()
    advance_ecology(e.world, e.access, 48, {"weather": "clear", "night": False})
    assert e.world.ecosystem.habitats == visited
    assert not e.world.ecosystem.animals


def test_animal_hunting_produces_finite_carcass(scene):
    e, a, _, _, p = scene
    animal = add_animal(e, p, health=4)
    assert act(e, a, Action.ATTACK, entity_id=animal.id)[0]
    assert animal.id not in e.world.ecosystem.animals
    assert sum(d.inventory.food for d in e.world.ecosystem.drops.values()) == 2
    assert not act(e, a, Action.ATTACK, entity_id=animal.id)[0]


def test_perception_does_not_leak_remote_ecology(scene):
    e, a, _, _, p = scene
    animal = add_animal(e, p)
    e.world.ecosystem.crops["local"] = Crop(id="local", position=p, owner_id=a.id, planted_tick=0)
    o = build_observation(e.world, a.id, access=e.access)
    assert len(o.animals) == len(o.crops) == 1
    animal.position = Position(x=-100, y=-100)
    e.world.ecosystem.crops["local"].position = animal.position.model_copy()
    o = build_observation(e.world, a.id, access=e.access)
    assert not o.animals and not o.crops


def test_policy_uses_local_crops_and_animal_produce(scene):
    e, a, _, _, p = scene
    e.world.ecosystem.crops["ripe"] = Crop(
        id="ripe", position=p, owner_id=a.id, planted_tick=0, growth=80
    )
    o = build_observation(e.world, a.id, access=e.access)
    i = e.policy.decide(o, preferred_goal="harvest_crop")
    assert i.action == Action.HARVEST and i.target == p
    add_animal(e, p, owner_id=a.id, trust=3)
    i = e.policy.decide(
        build_observation(e.world, a.id, access=e.access), preferred_goal="collect_animal"
    )
    assert i.action == Action.COLLECT


def test_policy_frees_material_space_before_a_real_harvest(scene):
    e, a, _, _, p = scene
    e.world.ecosystem.crops[f"crop:{p.x},{p.y}"] = Crop(
        id=f"crop:{p.x},{p.y}", position=p, owner_id=a.id, planted_tick=0, growth=80
    )
    a.inventory = Inventory(wood=7, capacity=8)
    a.hunger = 80
    i = e.policy.decide(build_observation(e.world, a.id, access=e.access))
    assert i.action == Action.DISCARD and i.decision.selected_goal == "make_harvest_space"
    assert resolve_intent(e.world, i, e.access)[0]
    i = e.policy.decide(build_observation(e.world, a.id, access=e.access))
    assert i.action == Action.HARVEST
    assert resolve_intent(e.world, i, e.access)[0]
    assert a.inventory.food == 3 and a.inventory.seeds == 2 and a.inventory.total == 8


def test_ecology_afterimages_replay_with_equal_hash(scene):
    e, a, b, _, p = scene
    add_animal(e, p)
    a.inventory.seeds = 2
    b.combat = CombatState()
    assert act(e, a, Action.TILL, target=p)[0]
    e.store.connection.execute(
        "UPDATE snapshots SET state=?,state_hash=? WHERE run_id=?",
        (json.dumps(authoritative_state(e.world)), state_hash(e.world), e.run_id),
    )
    e.store.connection.commit()
    events = e.tick([AgentIntent(actor_id=a.id, action=Action.PLANT, target=p)])
    assert any(v.event_type == "ECOSYSTEM_UPDATED" for v in events)
    e.tick([AgentIntent(actor_id=b.id, action=Action.ATTACK, peer_id=a.id)])
    assert state_hash(e.store.replay(e.run_id, use_snapshot=True)) == state_hash(e.world)


def test_legacy_world_omits_unassigned_new_fields():
    store = EventStore(":memory:")
    try:
        e = Engine(WorldConfig(infinite=True), store)
        data = authoritative_state(e.world)
        assert "ecosystem" not in data
        assert all("combat" not in a for a in data["agents"].values())
    finally:
        store.close()


def test_generated_ecology_replays_from_genesis_without_a_snapshot():
    store = EventStore(":memory:")
    try:
        e = Engine(WorldConfig(infinite=True, agent_count=3), store, UtilityPolicy())
        for _ in range(32):
            e.tick()
        assert e.world.ecosystem.habitats
        assert state_hash(store.replay(e.run_id)) == state_hash(e.world)
    finally:
        store.close()
