from app.simulation.models.domain import Episode
from app.simulation.settlements.environment import clamp, conditions


def remember(agent, episode):
    agent.memories = [*agent.memories, episode][-48:]


def experience(world, actor, intent, accepted, message, tick):
    if not world.config.infinite or actor is None or not actor.alive:
        return
    actor.cognition_source = intent.cognition_source
    if intent.thought:
        actor.thought = intent.thought
    goal = intent.decision.selected_goal if intent.decision else "observe"
    if not accepted or intent.action != "MOVE" or tick % 12 == 0:
        outcome = 0.3 if accepted else -0.8
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
            a.relationships[b.id] = clamp(a.relationships.get(b.id, 0.5) + 0.02)
            a.psychology.loneliness = clamp(a.psychology.loneliness - 0.05)
