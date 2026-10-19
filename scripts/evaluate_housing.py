"""Controlled housing comparison with real prototype actions and isolated in-memory worlds."""

import json

from app.simulation.engine.core import Engine
from app.simulation.engineering.housing import best_design
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import (
    Action,
    AgentIntent,
    Position,
    ShelterDesign,
    WorldConfig,
)
from app.simulation.persistence.sqlite import EventStore
from app.simulation.settlements import environment


def scenario(trials):
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True, agent_count=1), store)
    a = e.world.agents["agent-00"]
    a.position = Position(x=1, y=1)
    s = e.world.settlements[a.settlement_id]
    s.storage.capacity = 1000
    for item in ("food", "wood", "fiber", "stone"):
        setattr(s.storage, item, 100)
    design = ShelterDesign(
        frame="stone", roof="wood", bracing=True, raised_foundation=True
    )

    def step(intent):
        events = e.tick([intent])
        rejected = [
            event.payload["message"]
            for event in events
            if event.event_type == "ACTION_REJECTED"
        ]
        if rejected:
            raise RuntimeError(rejected)
        return events

    def upkeep():
        if a.hunger >= 55:
            return (
                AgentIntent(actor_id=a.id, action=Action.EAT)
                if a.inventory.food
                else AgentIntent(
                    actor_id=a.id, action=Action.WITHDRAW, item="food", amount=1
                )
            )
        if a.energy < 20:
            return AgentIntent(actor_id=a.id, action=Action.REST)
        return None

    for _ in range(trials * 3):
        while extra := upkeep():
            step(extra)
        step(AgentIntent(actor_id=a.id, action=Action.EXPERIMENT, design=design))
    assert best_design(a) == design
    # Normalize fatigue to compare construction experience, rather than time since last rest.
    while a.energy < 90:
        step(upkeep() or AgentIntent(actor_id=a.id, action=Action.REST))
    for _ in range(4):
        step(
            AgentIntent(
                actor_id=a.id,
                action=Action.BUILD,
                target=Position(x=1, y=2),
                building_kind="shelter",
                design=design,
            )
        )
    b = e.world.buildings["building:1:2"]
    before = b.durability
    initial_conditions = environment.conditions
    environment.conditions = lambda seed, tick: initial_conditions(seed, tick) | {
        "weather": "storm",
        "wind_strength": 0.99,
    }
    try:
        events = []
        for _ in range(120):
            events += step(upkeep() or AgentIntent(actor_id=a.id, action=Action.REST))
    finally:
        environment.conditions = initial_conditions
    result = {
        "prototype_work_actions": trials * 3,
        "retained_trials": len(a.housing.trials),
        "practice": a.housing.practice,
        "quality": b.quality,
        "initial_durability": before,
        "remaining_durability": b.durability,
        "storm_damage_events": sum(x.event_type == "BUILDING_DAMAGED" for x in events),
        "collapse_events": sum(x.event_type == "BUILDING_COLLAPSED" for x in events),
        "observed_lessons": a.housing.insights,
        "replay_matches": state_hash(store.replay(e.run_id)) == state_hash(e.world),
    }
    store.close()
    return result


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "conditions": "Supplied materials, one actor, same tested design, 120 storm ticks",
                "novice": scenario(1),
                "practiced": scenario(20),
            },
            indent=2,
        )
    )
