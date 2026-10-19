import asyncio
import json
import time
from pathlib import Path
from app.simulation.cognition.runtime import CognitionPolicy, Settings, Choice
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import authoritative_state, state_hash
from app.simulation.models.domain import WorldConfig, Position
from app.simulation.observation.builder import build_observation
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.utility import UtilityPolicy


async def main():
    store = EventStore(":memory:")
    e = Engine(WorldConfig(infinite=True), store)
    a, b = list(e.world.agents.values())[:2]
    for i, x in enumerate(e.world.agents.values()):
        x.position = Position(x=50 + i * 3, y=50)
    a.position = Position(x=0, y=0)
    b.position = Position(x=1, y=0)
    for x in [a, b]:
        x.hunger = 25
        x.energy = 80
        x.psychology.loneliness = 1
        x.personality.sociability = 1
    store.connection.execute(
        "UPDATE snapshots SET state=?, state_hash=? WHERE run_id=?",
        (json.dumps(authoritative_state(e.world)), state_hash(e.world), e.run_id),
    )
    store.connection.commit()
    p = CognitionPolicy(
        UtilityPolicy(),
        Settings(
            enabled=False,
            dialogue_provider="ollama",
            dialogue_url="http://localhost:11435/v1",
            dialogue_model="llama3.2:1b",
            timeout=90,
        ),
    )
    p.reset(e.run_id)
    result = {
        "model": "llama3.2:1b",
        "scenario": "Isolated adjacent agents; real local inference, not production run",
        "turns": [],
    }
    try:
        for actor in [a, b]:
            o = build_observation(e.world, actor.id, access=e.access)
            start = time.monotonic()
            p.schedule_dialogue(
                e.run_id, o, Choice(goal="socialize", reason="conversation"), {}
            )
            await asyncio.gather(*list(p.dialogue_tasks.values()))
            intent = p.decide(o)
            assert intent.utterance, p.status()
            events = e.tick([intent])
            d = next(x for x in events if x.event_type == "DIALOGUE")
            row = {
                "speaker": actor.name,
                "message": d.payload["message"],
                "seconds": round(time.monotonic() - start, 2),
            }
            result["turns"].append(row)
            print(row, flush=True)
        result["both_remember_both_turns"] = all(
            sum(m.kind == "dialogue" for m in x.memories) == 2 for x in [a, b]
        )
        result["replay_matches"] = state_hash(store.replay(e.run_id)) == state_hash(
            e.world
        )
        result["stats"] = p.status()
        Path("docs/evaluations/dialogue.json").write_text(json.dumps(result, indent=2))
        print(result, flush=True)
    finally:
        await p.close()
        store.close()


asyncio.run(main())
