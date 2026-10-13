import asyncio
import contextlib
import fcntl
from collections import deque
from pathlib import Path

from app.simulation.engine.core import Engine
from app.simulation.events.reducer import state_hash
from app.simulation.models.domain import WorldConfig
from app.simulation.persistence.sqlite import EventStore
from app.simulation.policies.rules import RulePolicy


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

    def remember(self, events):
        for e in events:
            if "message" in e.payload:
                self.recent.append(e.model_dump(mode="json"))

    def snapshot(self):
        return {
            "type": "snapshot",
            "run_id": self.engine.run_id,
            "sequence_number": self.engine.sequence,
            "tick_ms": 500 / self.engine.world.speed,
            "state": self.engine.world.model_dump(mode="json"),
            "state_hash": state_hash(self.engine.world),
            "events": list(self.recent),
        }

    def publish(self, events):
        self.remember(events)
        message = self.snapshot()
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
