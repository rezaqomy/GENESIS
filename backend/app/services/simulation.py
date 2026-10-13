import asyncio
import contextlib
import fcntl
import json
from collections import deque
from pathlib import Path

from app.simulation.chunks.access import ChunkCache, WorldAccess
from app.simulation.engine.core import Engine
from app.simulation.events.reducer import authoritative_state, state_hash
from app.simulation.models.domain import WorldConfig
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.rules import RulePolicy
from app.simulation.policies.utility import UtilityPolicy
from app.simulation.settlements.environment import conditions


class SimulationService:
    """One FIFO command queue and one writer task, shared by all HTTP/WS clients."""

    def __init__(self, database: str, config: WorldConfig):
        self.file_lock = None
        if database != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)
            self.file_lock = open(database + ".lock", "a")
            try:
                fcntl.flock(self.file_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.file_lock.close()
                raise RuntimeError("A Genesis process already owns this database") from None
        self.store = EventStore(database)
        self.engine = Engine(config, self.store, RulePolicy(), restore=True)
        if config.infinite and not self.engine.world.config.infinite:
            # Start an upgraded run while preserving every legacy event/run for replay.
            self.engine.reset(config)
        if self.engine.world.config.infinite:
            self.engine.policy = UtilityPolicy(
                self.engine.world.config.utility_weights.model_dump()
            )
        self.visual_cache = ChunkCache(
            self.engine.world.config.seed, self.engine.world.config.generator_version, 64
        )
        self.commands = asyncio.Queue()
        self.subscribers: set[asyncio.Queue] = set()
        self.recent = deque(maxlen=250)
        # Only display human-facing events; authoritative reducer events remain in SQLite.
        rows = self.store.connection.execute(
            "SELECT sequence_number FROM events WHERE run_id=? "
            "ORDER BY sequence_number DESC LIMIT 500",
            (self.engine.run_id,),
        ).fetchall()
        if rows:
            self.remember(self.store.events(self.engine.run_id, min(r[0] for r in rows) - 1))
        self.task: asyncio.Task | None = None

    @staticmethod
    def readable_event(event):
        data = event.model_dump(mode="json")
        data["payload"] = {
            key: value
            for key, value in data["payload"].items()
            if key in ("message", "action", "goal", "factors")
        }
        return data

    def remember(self, events):
        for e in events:
            if "message" in e.payload:
                self.recent.append(self.readable_event(e))

    def snapshot(self, update=False, new_events=None):
        world = self.engine.world
        metrics = {
            **self.engine.metrics,
            "active_chunks": len(self.engine.access.active_keys()) if world.config.infinite else 1,
            "loaded_chunks": len(self.engine.access.cache.entries) if world.config.infinite else 1,
            "visual_cached_chunks": len(self.visual_cache.entries),
            "payload_bytes": 0,
        }
        message = {
            "type": "entities" if update and world.config.infinite else "snapshot",
            "run_id": self.engine.run_id,
            "sequence_number": self.engine.sequence,
            "tick_ms": 500 / self.engine.world.speed,
            "state": authoritative_state(world)
            if world.config.infinite
            else world.model_dump(mode="json"),
            "environment": conditions(world.config.seed, world.tick),
            "metrics": metrics,
            "state_hash": state_hash(self.engine.world),
            "events": [self.readable_event(e) for e in new_events if "message" in e.payload]
            if new_events is not None
            else (list(self.recent)[-40:] if update else list(self.recent)),
        }
        message["metrics"]["payload_bytes"] = len(json.dumps(message, separators=(",", ":")))
        return message

    def chunk_projection(self, cx: int, cy: int):
        return WorldAccess(self.engine.world, self.visual_cache).projection(cx, cy)

    def chunk_message(self, coordinates: list[tuple[int, int]]):
        chunks = []
        codes = {
            "grass": "g",
            "forest": "f",
            "water": "w",
            "rock": "r",
            "soil": "s",
            "sand": "a",
            "mountain": "m",
            "path": "p",
        }
        for cx, cy in coordinates:
            chunk = self.chunk_projection(cx, cy)
            chunks.append(
                {
                    "key": chunk.key,
                    "cx": cx,
                    "cy": cy,
                    "generator_version": chunk.generator_version,
                    "terrain": "".join(codes[t.terrain.value] for t in chunk.tiles),
                    "walkable": "".join("1" if t.walkable else "0" for t in chunk.tiles),
                    "resources": {k: r.model_dump(mode="json") for k, r in chunk.resources.items()},
                }
            )
        return {
            "type": "chunks",
            "run_id": self.engine.run_id,
            "tick": self.engine.world.tick,
            "sequence_number": self.engine.sequence,
            "chunks": chunks,
        }

    def publish(self, events):
        self.remember(events)
        message = self.snapshot(update=True, new_events=events)
        for queue in self.subscribers:
            # Slow clients receive a fresh full state; they can retrieve older events by sequence.
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(message)

    async def submit(self, name: str, value=None):
        if self.task is None or self.task.done():
            raise RuntimeError("Simulation writer is unavailable")
        future = asyncio.get_running_loop().create_future()
        await self.commands.put((name, value, future))
        done, _ = await asyncio.wait((future, self.task), return_when=asyncio.FIRST_COMPLETED)
        if future in done:
            return future.result()
        future.cancel()
        raise RuntimeError("Simulation writer stopped before processing the command")

    async def run(self):
        while True:
            timeout = (
                0.5 / self.engine.world.speed if self.engine.world.status == "running" else None
            )
            try:
                name, value, future = await asyncio.wait_for(self.commands.get(), timeout=timeout)
            except TimeoutError:
                self.publish(self.engine.tick())
                continue
            try:
                if name == "reset":
                    config = self.engine.world.config.model_copy(update={"seed": value})
                    events = self.engine.reset(config)
                    events += [
                        self.engine.event(
                            "COMMAND_ACCEPTED",
                            {"command": "reset", "seed": value, "message": "Simulation: reset"},
                        )
                    ]
                    self.store.append(events[-1:])
                    self.recent.clear()
                    self.visual_cache = ChunkCache(config.seed, config.generator_version, 64)
                else:
                    events = self.engine.command(name, value)
                self.publish(events)
                if not future.done():
                    future.set_result(self.snapshot())
            except ValueError as exc:
                if not future.done():
                    future.set_exception(exc)

    def start(self):
        if self.task is not None and not self.task.done():
            raise RuntimeError("The authoritative writer is already running")
        self.task = asyncio.create_task(self.run(), name="genesis-authoritative-writer")

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        self.store.close()
        if self.file_lock:
            self.file_lock.close()
