"""One bounded perception range for decisions, social contact, and memory writes."""

from app.simulation.models.domain import Agent


def vision_radius(agent: Agent, effects: dict | None = None) -> int:
    # A nearby operational watchtower extends sight by four tiles, capped at twelve.
    bonus = 4 if effects and effects.get("visibility", 8) > 8 else 0
    return min(12, agent.vision_radius + bonus) if agent.alive else 0
