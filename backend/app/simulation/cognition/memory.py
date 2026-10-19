from app.simulation.cognition.tiers import (
    action_outcome,
    context_for,
    ensure_memory,
    learn,
    observe_food,
    retain,
)
from app.simulation.models.domain import Action, Episode, MemoryRecord
from app.simulation.settlements.environment import clamp, conditions


def remember(agent, episode):
    agent.memories = [*agent.memories, episode][-48:]


def experience(world, actor, intent, accepted, message, tick, before=None, access=None):
    if not world.config.infinite or actor is None or not actor.alive:
        return
    actor.cognition_source = intent.cognition_source
    actor.thought = intent.thought
    goal = intent.decision.selected_goal if intent.decision else "observe"
    env = conditions(world.config.seed, tick)
    context = context_for(actor, env)
    outcome = action_outcome(actor, intent, accepted, before)
    record = MemoryRecord(
        id=f"{tick}:{actor.id}:{intent.action}",
        tick=tick,
        kind="action" if accepted else "failure",
        text=message[:500],
        goal=goal,
        action=intent.action,
        context=context,
        outcome=outcome,
        importance=min(1, 0.2 + abs(outcome) * 0.65),
        position=before["position"] if before else actor.position.model_copy(),
        target=intent.target,
    )
    # Recent positions already cover each move; sample routine travel to save attention/bandwidth.
    if not accepted or intent.action != Action.MOVE or tick % 12 == 0:
        retain(actor, record)
    learn(actor, record)
    memory = ensure_memory(actor)
    memory.recalled_ids = list(intent.recalled_ids)
    if accepted and intent.action == Action.GATHER:
        resource = (
            access.resource(intent.resource_id or "")
            if access is not None
            else world.resources.get(intent.resource_id or "")
        )
        if resource is not None:
            observe_food(actor, [resource], tick)
    if not accepted or intent.action != "MOVE" or tick % 12 == 0:
        remember(
            actor,
            Episode(
                tick=tick,
                kind="action" if accepted else "failure",
                text=message[:500],
                goal=goal,
                outcome=outcome,
            ),
        )
        if intent.action not in (Action.MOVE, Action.IDLE):
            actor.habits = {
                **actor.habits,
                goal: round(max(-1, min(1, actor.habits.get(goal, 0) * 0.9 + outcome * 0.1)), 4),
            }
        actor.psychology.stress = clamp(actor.psychology.stress + (0 if accepted else 0.03))
    if tick % 24 == 0:
        env = conditions(world.config.seed, tick)
        remember(
            actor,
            Episode(
                tick=tick,
                kind="environment",
                text=f"{env['weather']}; {'night' if env['night'] else 'day'}; "
                f"safety {actor.psychology.sense_of_safety:.2f}",
            ),
        )
    if accepted and intent.utterance and intent.peer_id:
        peer = world.agents[intent.peer_id]  # Resolver validated this specific listener.
        text = f"{actor.name} to {peer.name}: {intent.utterance}"
        remember(
            actor,
            Episode(tick=tick, kind="dialogue", text=text[:500], peer_id=peer.id, outcome=0.4),
        )
        remember(
            peer,
            Episode(tick=tick, kind="dialogue", text=text[:500], peer_id=actor.id, outcome=0.4),
        )
        for a, b in ((actor, peer), (peer, actor)):
            retain(
                a,
                MemoryRecord(
                    id=f"{tick}:dialogue:{actor.id}:{peer.id}",
                    tick=tick,
                    kind="dialogue",
                    text=text[:500],
                    goal="socialize",
                    action=Action.SOCIALIZE,
                    context=context_for(a, env),
                    outcome=0.4,
                    importance=0.7,
                    position=a.position.model_copy(),
                    peer_id=b.id,
                ),
            )
            a.relationships[b.id] = clamp(a.relationships.get(b.id, 0.5) + 0.02)
            a.psychology.loneliness = clamp(a.psychology.loneliness - 0.05)
