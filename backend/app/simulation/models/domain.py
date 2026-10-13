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
    SAND = "sand"
    MOUNTAIN = "mountain"
    PATH = "path"


class Action(StrEnum):
    MOVE = "MOVE"
    GATHER = "GATHER"
    EAT = "EAT"
    REST = "REST"
    IDLE = "IDLE"
    SOCIALIZE = "SOCIALIZE"
    STORE = "STORE"
    WITHDRAW = "WITHDRAW"
    CRAFT = "CRAFT"
    BUILD = "BUILD"
    REFUEL = "REFUEL"


class Tile(Model):
    position: Position
    terrain: Terrain
    walkable: bool


class Resource(Model):
    id: str
    position: Position
    kind: Literal["food", "wood", "stone", "fiber", "clay", "ore", "fuel", "water", "seeds"]
    quantity: int = Field(ge=0)
    capacity: int = Field(gt=0)


RESOURCE_KINDS = ("food", "wood", "stone", "fiber", "clay", "ore", "fuel", "water", "seeds")


class Inventory(Model):
    food: int = Field(default=0, ge=0)
    wood: int = Field(default=0, ge=0)
    stone: int = Field(default=0, ge=0)
    fiber: int = Field(default=0, ge=0)
    clay: int = Field(default=0, ge=0)
    ore: int = Field(default=0, ge=0)
    fuel: int = Field(default=0, ge=0)
    water: int = Field(default=0, ge=0)
    seeds: int = Field(default=0, ge=0)
    tools: dict[str, int] = Field(default_factory=dict)
    capacity: int = Field(default=8, gt=0)

    @property
    def total(self) -> int:
        return sum(getattr(self, key) for key in RESOURCE_KINDS) + sum(
            v > 0 for v in self.tools.values()
        )


class Personality(Model):
    sociability: float = Field(default=0.5, ge=0, le=1)
    curiosity: float = Field(default=0.5, ge=0, le=1)
    risk_tolerance: float = Field(default=0.5, ge=0, le=1)
    independence: float = Field(default=0.5, ge=0, le=1)
    cooperation: float = Field(default=0.5, ge=0, le=1)
    ambition: float = Field(default=0.5, ge=0, le=1)
    resourcefulness: float = Field(default=0.5, ge=0, le=1)
    loyalty: float = Field(default=0.5, ge=0, le=1)
    comfort_preference: float = Field(default=0.5, ge=0, le=1)
    exploration_drive: float = Field(default=0.5, ge=0, le=1)


class Psychology(Model):
    loneliness: float = Field(default=0.1, ge=0, le=1)
    fear: float = Field(default=0.1, ge=0, le=1)
    stress: float = Field(default=0.1, ge=0, le=1)
    mood: float = Field(default=0.7, ge=0, le=1)
    sense_of_safety: float = Field(default=0.8, ge=0, le=1)
    satisfaction: float = Field(default=0.5, ge=0, le=1)
    homesickness: float = Field(default=0, ge=0, le=1)
    attachment: float = Field(default=0.4, ge=0, le=1)
    social_satisfaction: float = Field(default=0.6, ge=0, le=1)


class CandidateGoal(Model):
    goal: str
    utility: float = Field(ge=0, le=1)
    factors: dict[str, float] = Field(default_factory=dict)
    rejection: str | None = None


class Decision(Model):
    selected_goal: str = "observe"
    candidates: list[CandidateGoal] = Field(default_factory=list)
    factors: dict[str, float] = Field(default_factory=dict)
    plan: list[str] = Field(default_factory=list)
    selected_tick: int = 0
    commitment_until: int = 0
    target: Position | None = None
    progress: float = Field(default=0, ge=0, le=1)
    origin_distance: int = 0
    cooldowns: dict[str, int] = Field(default_factory=dict)
    failures: int = 0


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
    personality: Personality = Field(default_factory=Personality)
    psychology: Psychology = Field(default_factory=Psychology)
    decision: Decision = Field(default_factory=Decision)
    settlement_id: str | None = None
    home: Position = Field(default_factory=lambda: Position(x=0, y=0))
    known_chunks: list[str] = Field(default_factory=list)
    discoveries: list[Position] = Field(default_factory=list)
    known_resources: list[Resource] = Field(
        default_factory=list
    )  # Early Phase 2 development save compatibility.
    recent_positions: list[Position] = Field(default_factory=list)
    food_memory: dict[str, int] = Field(default_factory=dict)
    exploration_steps: int = 0
    time_away: int = 0
    lifestyle: Literal["settler", "wanderer"] = "settler"
    nearby_agents: list[str] = Field(default_factory=list)
    relationships: dict[str, float] = Field(default_factory=dict)


class UtilityWeights(Model):
    need: float = Field(default=0.55, ge=0, le=1)
    trait: float = Field(default=0.25, ge=0, le=1)
    reward: float = Field(default=0.20, ge=0, le=1)
    travel: float = Field(default=0.18, ge=0, le=1)
    risk: float = Field(default=0.22, ge=0, le=1)
    social: float = Field(default=0.15, ge=0, le=1)
    scarcity: float = Field(default=0.24, ge=0, le=1)


class WorldConfig(Model):
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    infinite: bool = False  # Legacy saves/tests remain valid; the application opts into chunks.
    generator_version: int = Field(default=2, ge=1, le=2)
    chunk_size: Literal[32] = 32
    active_radius: int = Field(default=1, ge=0, le=2)
    chunk_cache_size: int = Field(default=64, ge=16, le=256)
    utility_weights: UtilityWeights = Field(default_factory=UtilityWeights)
    path_budget: int = Field(default=600, ge=50, le=2000)
    width: int = Field(default=40, ge=12, le=80)
    height: int = Field(default=30, ge=12, le=60)
    agent_count: int = Field(default=10, ge=1, le=30)
    regeneration_ticks: int = Field(default=20, ge=0, le=10000)


class ResourceModification(Model):
    quantity: int = Field(ge=0)
    tick: int = Field(ge=0)
    capacity: int = Field(default=8, gt=0)


class Chunk(Model):
    key: str
    cx: int
    cy: int
    generator_version: int
    tiles: list[Tile]
    resources: dict[str, Resource]


class Building(Model):
    id: str
    kind: Literal[
        "campfire",
        "shelter",
        "storage",
        "workbench",
        "farm",
        "wooden_wall",
        "stone_wall",
        "watchtower",
        "bridge",
        "road",
        "remote_camp",
    ]
    position: Position
    settlement_id: str | None = None
    owner_id: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    durability: int = Field(default=100, ge=0, le=100)
    fuel: int = Field(default=0, ge=0, le=100)
    food: int = Field(default=0, ge=0)
    created_tick: int = 0


class Settlement(Model):
    id: str
    name: str
    center: Position
    members: list[str] = Field(default_factory=list)
    storage: Inventory = Field(default_factory=lambda: Inventory(capacity=80))
    buildings: list[str] = Field(default_factory=list)
    food_reserves: int = 0
    safety: float = Field(default=0, ge=0, le=1)
    comfort: float = Field(default=0, ge=0, le=1)
    resource_availability: float = Field(default=0, ge=0, le=1)
    social_cohesion: float = Field(default=0, ge=0, le=1)
    influence: float = Field(default=6, ge=0)
    crowding: float = Field(default=0, ge=0, le=1)
    exploration_activity: int = 0


class WorldState(Model):
    config: WorldConfig
    tick: int = 0
    status: Literal["running", "paused"] = "paused"
    speed: float = 1
    tiles: list[Tile]
    agents: dict[str, Agent]
    resources: dict[str, Resource]
    resource_modifications: dict[str, ResourceModification] = Field(default_factory=dict)
    terrain_modifications: dict[str, Tile] = Field(default_factory=dict)
    explored_chunks: list[str] = Field(default_factory=list)
    settlements: dict[str, Settlement] = Field(default_factory=dict)
    buildings: dict[str, Building] = Field(default_factory=dict)


class AgentIntent(Model):
    actor_id: str
    action: Action
    target: Position | None = None
    resource_id: str | None = None
    destination: Position | None = None
    decision: Decision | None = None
    item: str | None = None
    amount: int = Field(default=1, ge=1, le=8)
    building_kind: str | None = None
    building_id: str | None = None
