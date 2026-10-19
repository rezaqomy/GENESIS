from typing import Literal

from pydantic import Field

from app.simulation.events.reducer import WorldEvent
from app.simulation.models.domain import Model, WorldState


class ResetRequest(Model):
    seed: int = Field(default=42, ge=0, le=2**32 - 1)


class SpeedRequest(Model):
    multiplier: Literal[0.5, 1, 2, 4, 8]


class Snapshot(Model):
    type: Literal["snapshot"] = "snapshot"
    run_id: str
    sequence_number: int
    tick_ms: float
    state: WorldState
    state_hash: str
    events: list[WorldEvent]
    events_after: int | None = None
    environment: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)


class HealthResponse(Model):
    status: str


class EventsResponse(Model):
    run_id: str
    events: list[WorldEvent]
    next_sequence: int


class ReplayResponse(Model):
    run_id: str
    state: WorldState
    state_hash: str
