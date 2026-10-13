import json
import sqlite3

from app.simulation.events.reducer import WorldEvent, reduce_event, state_hash
from app.simulation.models.domain import WorldState


class EventStore:
    def __init__(self, path: str):
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, sequence_number INTEGER NOT NULL,
                tick INTEGER NOT NULL, event_type TEXT NOT NULL, actor_id TEXT,
                payload TEXT NOT NULL, schema_version INTEGER NOT NULL,
                UNIQUE(run_id, sequence_number));
            CREATE TABLE IF NOT EXISTS snapshots (
                run_id TEXT NOT NULL, sequence_number INTEGER NOT NULL,
                tick INTEGER NOT NULL, state TEXT NOT NULL, state_hash TEXT NOT NULL,
                PRIMARY KEY(run_id, sequence_number));
            CREATE INDEX IF NOT EXISTS events_run_tick ON events(run_id, tick);
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'Event log is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT, 'Event log is append-only'); END;
        """)

    def append(self, events: list[WorldEvent], snapshot: WorldState | None = None) -> None:
        with self.connection:
            for e in events:
                self.connection.execute(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        e.event_id,
                        e.run_id,
                        e.sequence_number,
                        e.tick,
                        e.event_type,
                        e.actor_id,
                        json.dumps(e.payload),
                        e.schema_version,
                    ),
                )
            if snapshot is not None and events:
                e = events[-1]
                self.connection.execute(
                    "INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)",
                    (
                        e.run_id,
                        e.sequence_number,
                        snapshot.tick,
                        snapshot.model_dump_json(),
                        state_hash(snapshot),
                    ),
                )

    def events(self, run_id: str, after: int = 0, limit: int = 1000) -> list[WorldEvent]:
        rows = self.connection.execute(
            "SELECT * FROM events WHERE run_id=? AND sequence_number>? "
            "ORDER BY sequence_number LIMIT ?",
            (run_id, after, limit),
        ).fetchall()
        return [
            WorldEvent(
                event_id=r[0],
                run_id=r[1],
                sequence_number=r[2],
                tick=r[3],
                event_type=r[4],
                actor_id=r[5],
                payload=json.loads(r[6]),
                schema_version=r[7],
            )
            for r in rows
        ]

    def latest_run(self) -> str | None:
        row = self.connection.execute(
            "SELECT run_id FROM events ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def sequence(self, run_id: str) -> int:
        return self.connection.execute(
            "SELECT COALESCE(MAX(sequence_number), 0) FROM events WHERE run_id=?", (run_id,)
        ).fetchone()[0]

    def replay(self, run_id: str, use_snapshot: bool = False) -> WorldState:
        world = None
        after = 0
        if use_snapshot:
            row = self.connection.execute(
                "SELECT sequence_number, state, state_hash FROM snapshots WHERE run_id=? "
                "ORDER BY sequence_number DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            if row:
                after = row[0]
                world = WorldState.model_validate_json(row[1])
                if state_hash(world) != row[2]:
                    raise ValueError("Snapshot hash mismatch")
        while events := self.events(run_id, after):
            for event in events:
                world = reduce_event(world, event)
                after = event.sequence_number
        if world is None:
            raise ValueError("Unknown run")
        return world

    def close(self) -> None:
        self.connection.close()
