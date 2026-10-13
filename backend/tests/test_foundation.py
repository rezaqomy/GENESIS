from app.simulation.actions.resolver import advance_physiology, resolve_intent
from app.simulation.engine.generation import generate_world
from app.simulation.models.domain import Action, AgentIntent, Position, WorldConfig


def test_seeded_generation():
    a = generate_world(WorldConfig())
    assert a == generate_world(WorldConfig())
    assert a != generate_world(WorldConfig(seed=43))
    assert len(a.tiles) == 1200 and len(a.agents) == 10
    assert len({(a.position.x, a.position.y) for a in a.agents.values()}) == 10


def test_actions():
    w = generate_world(WorldConfig())
    a = next(iter(w.agents.values()))
    r = next(iter(w.resources.values()))
    a.position = r.position.model_copy()
    assert resolve_intent(w, AgentIntent(actor_id=a.id, action=Action.GATHER, resource_id=r.id))[0]
    assert r.quantity == r.capacity - 1
    assert a.inventory.total == 1
    a.inventory.food = 1
    a.hunger = 80
    assert resolve_intent(w, AgentIntent(actor_id=a.id, action=Action.EAT))[0]
    assert a.hunger == 45 and a.inventory.food == 0
    a.energy = 0
    assert resolve_intent(w, AgentIntent(actor_id=a.id, action=Action.REST))[0]
    assert a.energy == 14
    assert not resolve_intent(
        w, AgentIntent(actor_id=a.id, action=Action.MOVE, target=Position(x=-1, y=-1))
    )[0]


def test_starvation():
    w = generate_world(WorldConfig())
    a = next(iter(w.agents.values()))
    a.hunger = 99
    a.health = 3
    advance_physiology(w)
    assert a.hunger == 100 and a.health == 0 and not a.alive
