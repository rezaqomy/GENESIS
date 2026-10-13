from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Position(Model):
    x: int
    y: int

    def distance(self, other: "Position") -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)


class Terrain(StrEnum):
    GRASS = "grass"
    FOREST = "forest"
    WATER = "water"
    ROCK = "rock"
    SOIL = "soil"


class Action(StrEnum):
    MOVE = "MOVE"
    GATHER = "GATHER"
    EAT = "EAT"
    REST = "REST"
    IDLE = "IDLE"


class Tile(Model):
    position: Position
    terrain: Terrain
    walkable: bool


class Resource(Model):
    id: str
    position: Position
    kind: Literal["food", "wood"]
    quantity: int = Field(ge=0)
    capacity: int = Field(gt=0)


class Inventory(Model):
    food: int = Field(default=0, ge=0)
    wood: int = Field(default=0, ge=0)
    capacity: int = Field(default=8, gt=0)

    @property
    def total(self) -> int:
        return self.food + self.wood


class Agent(Model):
    id: str
    name: str
    age: int
    visual_color: str
    health: int = Field(default=100, ge=0, le=100)
    hunger: int = Field(default=20, ge=0, le=100)  # 100 = starving
    energy: int = Field(default=100, ge=0, le=100)
    position: Position
    inventory: Inventory = Field(default_factory=Inventory)
    destination: Position | None = None
    current_action: Action = Action.IDLE
    alive: bool = True


class WorldConfig(Model):
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    width: int = Field(default=40, ge=12, le=80)
    height: int = Field(default=30, ge=12, le=60)
    agent_count: int = Field(default=10, ge=1, le=30)
    regeneration_ticks: int = Field(default=20, ge=0, le=10000)


class WorldState(Model):
    config: WorldConfig
    tick: int = 0
    status: Literal["running", "paused"] = "paused"
    speed: float = 1
    tiles: list[Tile]
    agents: dict[str, Agent]
    resources: dict[str, Resource]


class AgentIntent(Model):
    actor_id: str
    action: Action
    target: Position | None = None
    resource_id: str | None = None
    destination: Position | None = None
