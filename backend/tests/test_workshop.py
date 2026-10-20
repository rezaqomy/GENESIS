import pytest

from app.simulation.actions.resolver import resolve_intent
from app.simulation.actions.workshop import fisheries
from app.simulation.engine.core import Engine
from app.simulation.engineering import assemblies
from app.simulation.events.reducer import (
    WorldEvent,
    agent_state,
    authoritative_state,
    reduce_event,
    settlement_state,
    state_hash,
)
from app.simulation.models.domain import (
    Action,
    Agent,
    AgentIntent,
    AssemblyDesign,
    AssemblyPart,
    Building,
    Inventory,
    Position,
    Settlement,
    Terrain,
    Tile,
    TradeOffer,
    WorldConfig,
)
from app.simulation.observation.builder import build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


@pytest.fixture
def setup():
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), store, UtilityPolicy())
    a = next(iter(e.world.agents.values()))
    a.position = Position(x=1, y=0)
    a.inventory.capacity = 100
    for m in ("wood", "stone", "clay", "fiber", "ore", "food", "fuel", "seeds", "water"):
        setattr(a.inventory, m, 6)
    a.hunger = 10
    yield e, a
    store.close()


def trap():
    return AssemblyDesign(
        name="river basket",
        parts=[
            AssemblyPart(material="fiber", shape="mesh", count=2),
            AssemblyPart(material="wood", shape="rod"),
        ],
        joint="fiber",
    )


def kiln():
    return AssemblyDesign(
        name="sealed chamber",
        parts=[
            AssemblyPart(material="stone", shape="bowl", count=2),
            AssemblyPart(material="clay", shape="plate"),
        ],
        joint="clay",
        mechanism="combustion",
        enclosed=True,
    )


def test_design(e, a, design):
    intent = AgentIntent(actor_id=a.id, action=Action.EXPERIMENT_ASSEMBLY, assembly_design=design)
    for _ in range(3):
        assert resolve_intent(e.world, intent, e.access)[0]
    return a.workshop.trials[-1]


# This helper performs real trials; it is not itself a pytest test case.
test_design.__test__ = False


def empty_site(e, a):
    for y in range(-8, 9):
        for x in range(-8, 9):
            p = Position(x=x, y=y)
            if (
                e.access.tile(p).walkable
                and not e.access.visible_resources(p, 0)
                and not any(b.position == p for b in e.world.buildings.values())
                and not any(v.alive and v.position == p for v in e.world.agents.values())
            ):
                a.position = Position(x=x - 1, y=y)
                return p
    pytest.fail("No empty site")


def build(e, a, design):
    site = empty_site(e, a)
    intent = AgentIntent(actor_id=a.id, action=Action.ASSEMBLE, target=site, assembly_design=design)
    assert resolve_intent(e.world, intent, e.access)[0]
    return e.world.buildings[f"building:{site.x}:{site.y}"]


def test_physical_design_not_label_and_paid_trials_before_fabrication(setup):
    e, a = setup
    d = trap()
    renamed = d.model_copy(update={"name": "magic infinite food machine"})
    assert assemblies.design_id(d) == assemblies.design_id(renamed)
    assert assemblies.evaluate(d) == assemblies.evaluate(renamed)
    assert not resolve_intent(
        e.world,
        AgentIntent(actor_id=a.id, action=Action.ASSEMBLE, target=a.position, assembly_design=d),
        e.access,
    )[0]
    before = a.inventory.fiber
    intent = AgentIntent(actor_id=a.id, action=Action.EXPERIMENT_ASSEMBLY, assembly_design=d)
    assert resolve_intent(e.world, intent, e.access)[0]
    assert a.inventory.fiber == before - 3
    assert not a.workshop.trials
    assert resolve_intent(e.world, intent, e.access)[0]
    assert resolve_intent(e.world, intent, e.access)[0]
    assert a.inventory.fiber == before - 3
    assert a.workshop.trials[-1].measured["catch"] >= 0.3
    a.inventory.fiber = 6
    b = build(e, a, d)
    assert b.assembly.design == d
    assert a.inventory.fiber == 3  # A deployed device is not a free copy of its prototype.


def test_failure_feedback_and_planning_do_not_call_hidden_physics(setup, monkeypatch):
    e, a = setup
    bad = AssemblyDesign(
        parts=[AssemblyPart(material="wood", shape="bowl")], mechanism="combustion"
    )
    t = test_design(e, a, bad)
    assert t.measured["heat"] < 0.3
    assert any("charred" in f for f in t.feedback)
    before = a.model_dump_json()
    monkeypatch.setattr(assemblies, "evaluate", lambda *_: pytest.fail("Planner used oracle"))
    proposals = [
        assemblies.propose(a, 42, tick, {m: 9 for m in assemblies.MATERIALS}, "heat")
        for tick in range(0, 180, 18)
    ]
    assert len({assemblies.design_id(d) for d in proposals}) > 3
    e.policy.decide(build_observation(e.world, a.id, access=e.access))
    assert a.model_dump_json() == before


def test_fishing_is_local_and_shares_finite_recovering_stock(setup):
    e, a = setup
    test_design(e, a, trap())
    b = build(e, a, trap())
    water = Position(x=b.position.x + 1, y=b.position.y)
    e.world.terrain_modifications[f"{water.x},{water.y}"] = Tile(
        position=water, terrain=Terrain.WATER, walkable=False
    )
    a.inventory.food = 0
    use = AgentIntent(
        actor_id=a.id, action=Action.OPERATE, building_id=b.id, item="catch", target=water
    )
    for i in range(4):
        e.world.tick = i * 24
        assert resolve_intent(e.world, use, e.access)[0]
        assert not resolve_intent(e.world, use, e.access)[0]  # Shared device cooldown.
    e.world.tick = 120
    assert not resolve_intent(e.world, use, e.access)[0]
    assert a.inventory.food == 4 and fisheries(e.world, water)[1] == 0
    e.world.tick = 600
    assert resolve_intent(e.world, use, e.access)[0]
    a.position = Position(x=100, y=100)
    assert not resolve_intent(e.world, use, e.access)[0]


def test_heat_discovery_consumes_inputs_and_unlocks_materials_not_free_recipes(setup):
    e, a = setup
    fire = Building(id="testfire", kind="campfire", position=a.position, progress=100, fuel=5)
    e.world.buildings[fire.id] = fire
    before = a.inventory.ore
    heat = AgentIntent(actor_id=a.id, action=Action.HEAT, building_id=fire.id, item="ore")
    assert resolve_intent(e.world, heat, e.access)[0]
    assert a.inventory.ore == before - 1 and not a.inventory.products.get("metal")
    assert "insufficient heat" in a.workshop.transformations["ore:low"]
    test_design(e, a, kiln())
    b = build(e, a, kiln())
    heat.building_id = b.id
    assert resolve_intent(e.world, heat, e.access)[0]
    assert a.inventory.products["metal"] == 1 and a.workshop.transformations["ore:hot"] == "metal"
    heat.item = "clay"
    assert resolve_intent(e.world, heat, e.access)[0]
    assert a.inventory.products["ceramic"] == 1
    heat.item = "food"
    assert resolve_intent(e.world, heat, e.access)[0]
    a.inventory.food, a.hunger = 0, 70
    assert resolve_intent(e.world, AgentIntent(actor_id=a.id, action=Action.EAT), e.access)[0]
    assert a.hunger == 20 and a.inventory.products["cooked_food"] == 0


def test_idea_is_only_shared_by_actual_local_speech_and_requires_paid_test(setup):
    e, a = setup
    b = list(e.world.agents.values())[1]
    b.position = Position(x=a.position.x + 1, y=a.position.y)
    proposal = AgentIntent(
        actor_id=a.id,
        action=Action.SOCIALIZE,
        peer_id=b.id,
        utterance="Could a woven basket catch food by the river?",
        idea=trap(),
    )
    assert resolve_intent(e.world, proposal, e.access)[0]
    assert a.workshop.proposals == b.workshop.proposals == [trap()]
    assert not a.workshop.trials and not b.workshop.trials
    assert not resolve_intent(
        e.world,
        AgentIntent(
            actor_id=b.id, action=Action.ASSEMBLE, target=b.position, assembly_design=trap()
        ),
        e.access,
    )[0]
    b.position = Position(x=50, y=50)
    assert not resolve_intent(e.world, proposal, e.access)[0]


def test_barter_requires_offer_acceptance_current_goods_capacity_and_proximity(setup):
    e, a = setup
    b = list(e.world.agents.values())[1]
    b.position = Position(x=2, y=0)
    b.inventory.fiber, b.inventory.wood = 3, 0
    offer = TradeOffer(id="swap", peer_id=b.id, give_item="wood", want_item="fiber", expires=96)
    proposal = AgentIntent(actor_id=a.id, action=Action.OFFER_TRADE, peer_id=b.id, trade=offer)
    before = a.inventory.wood
    assert resolve_intent(e.world, proposal, e.access)[0]
    assert a.inventory.wood == before and b.inventory.wood == 0
    accept = AgentIntent(actor_id=b.id, action=Action.ACCEPT_TRADE, peer_id=a.id, item="swap")
    assert resolve_intent(e.world, accept, e.access)[0]
    assert a.inventory.wood == before - 1 and b.inventory.wood == 1
    assert b.inventory.fiber == 2 and a.inventory.fiber == 7
    assert not resolve_intent(e.world, accept, e.access)[0]
    assert resolve_intent(e.world, proposal, e.access)[0]
    b.position = Position(x=50, y=50)
    assert not resolve_intent(e.world, accept, e.access)[0]
    assert all(
        p.get("trade_offer") is None
        for p in build_observation(e.world, b.id, access=e.access).peers
    )


def test_salvage_once_and_only_by_owner(setup):
    e, a = setup
    test_design(e, a, kiln())
    b = build(e, a, kiln())
    before = a.inventory.stone
    salvage = AgentIntent(actor_id=a.id, action=Action.DISMANTLE, building_id=b.id)
    assert resolve_intent(e.world, salvage, e.access)[0]
    assert a.inventory.stone == before + 1 and b.salvaged and not b.durability
    assert not resolve_intent(e.world, salvage, e.access)[0]
    assert a.inventory.stone == before + 1


def test_legacy_field_presence_and_full_workshop_replay(setup):
    e, a = setup
    old_agent = agent_state(a)
    old_agent.pop("workshop", None)
    old_agent["inventory"].pop("products", None)
    assert agent_state(Agent.model_validate(old_agent)) == old_agent
    s = next(iter(e.world.settlements.values()))
    old_s = settlement_state(s)
    old_s["storage"].pop("products", None)
    assert settlement_state(Settlement.model_validate(old_s)) == old_s
    initial = authoritative_state(e.world)
    replay = reduce_event(
        None,
        WorldEvent(
            run_id=e.run_id,
            sequence_number=0,
            tick=0,
            event_type="WORLD_CREATED",
            payload={"state": initial},
        ),
    )
    intent = AgentIntent(actor_id=a.id, action=Action.EXPERIMENT_ASSEMBLY, assembly_design=kiln())
    for _ in range(3):
        for event in e.tick([intent]):
            replay = reduce_event(replay, event)
    assert state_hash(replay) == state_hash(e.world)
    assert a.workshop.trials[-1].measured["heat"] >= 0.7


def test_products_count_towards_capacity_and_must_be_nonnegative():
    inv = Inventory(food=1, products={"metal": 2, "ceramic": 1})
    assert inv.total == 4
    with pytest.raises(ValueError):
        Inventory(products={"metal": -1})


def test_device_materials_are_hauled_and_not_immediately_stored_again(setup):
    e, a = setup
    test_design(e, a, trap())
    s = e.world.settlements[a.settlement_id]
    a.position = s.center.model_copy()
    a.inventory.fiber = 0
    s.storage.fiber = 6
    a.inventory.food = 2
    a.energy = 90
    # The writer accepts a stock withdrawal only for a personally tested plan.
    intent = AgentIntent(
        actor_id=a.id, action=Action.WITHDRAW, item="fiber", amount=3, assembly_design=trap()
    )
    assert resolve_intent(e.world, intent, e.access)[0]
    assert a.workshop.planned == trap()
    from app.simulation.policies.economy import settlement_goals

    plans = []

    def capture(goal, *args, **kw):
        plans.append((goal, kw))

    settlement_goals(
        build_observation(e.world, a.id, access=e.access),
        capture,
        capture,
        {(a.position.x, a.position.y)},
    )
    assert not any(goal == "store_resources" and kw.get("item") == "fiber" for goal, kw in plans)
    old = agent_state(a)
    old["workshop"].pop("planned")
    assert agent_state(Agent.model_validate(old)) == old


def test_experimental_devices_weather_and_damage_is_local(setup):
    from app.simulation.engineering.weathering import weather_damage

    e, a = setup
    test_design(e, a, trap())
    b = build(e, a, trap())
    b.durability = 2
    distant = list(e.world.agents.values())[1]
    distant.position = Position(x=100, y=100)
    before = len(distant.memory.long_term) if distant.memory else 0
    events = weather_damage(e.world, 12, {"weather": "storm", "wind_strength": 1})
    assert b.durability == 0
    assert any(event[0] == "BUILDING_COLLAPSED" for event in events)
    assert any("collapsed" in m.text for m in a.memory.long_term)
    assert (len(distant.memory.long_term) if distant.memory else 0) == before


@pytest.mark.asyncio
async def test_model_idea_survives_async_mailbox_and_becomes_an_untested_shared_proposal(setup):
    import json

    import httpx

    from app.simulation.cognition.runtime import Choice, CognitionPolicy, Settings

    e, a = setup
    b = list(e.world.agents.values())[1]
    b.position = Position(x=2, y=0)
    p = CognitionPolicy(
        e.policy,
        Settings(enabled=False, dialogue_url="https://speech.test/v1", dialogue_model="test"),
    )
    p.reset(e.run_id)
    await p.client.aclose()
    p.client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "text": "Let's test this basket beside the river.",
                                        "idea": trap().model_dump(),
                                    }
                                )
                            }
                        }
                    ]
                },
            )
        )
    )
    try:
        observation = build_observation(e.world, a.id, access=e.access)
        await p.infer_dialogue(e.run_id, observation, Choice(goal="socialize", reason="idea"), {})
        intent = p.decide(observation)
        assert intent.idea == trap() and intent.utterance
        assert resolve_intent(e.world, intent, e.access)[0]
        assert a.workshop.proposals[-1] == b.workshop.proposals[-1] == trap()
        assert not a.workshop.trials and not a.inventory.products
    finally:
        await p.close()


def test_invalid_model_idea_does_not_erase_valid_speech_or_grant_a_design():
    import json

    from app.simulation.cognition.runtime import decode_speech

    speech, rejected = decode_speech(
        json.dumps({"text": "Could we try another joint?", "idea": {"name": "infinite generator"}})
    )
    assert rejected and speech.text == "Could we try another joint?" and speech.idea is None
    with pytest.raises(ValueError):
        decode_speech('{"text":42}')
