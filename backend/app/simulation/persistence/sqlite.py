import base64
import json
import sqlite3
import zlib
from contextlib import contextmanager

from app.simulation.events.reducer import WorldEvent, authoritative_state, reduce_event, state_hash
from app.simulation.models.domain import WorldState


class EventStore:
    def __init__(self, path: str):
        self.connection = sqlite3.connect(path)
        self.transaction_depth = 0
        self.connection.execute("PRAGMA auto_vacuum=FULL")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS history_aggregates (
                run_id TEXT, bucket INTEGER, event_type TEXT, actor_id TEXT, action TEXT,
                count INTEGER, first_tick INTEGER, last_tick INTEGER, examples TEXT,
                PRIMARY KEY(run_id,bucket,event_type,actor_id,action));
            CREATE TABLE IF NOT EXISTS history_metadata (
                run_id TEXT PRIMARY KEY, through_sequence INTEGER, through_tick INTEGER,
                state_hash TEXT, original_events INTEGER);
            CREATE TABLE IF NOT EXISTS history_journal (
                run_id TEXT, sequence_number INTEGER, tick INTEGER, event_type TEXT,
                actor_id TEXT, payload TEXT, PRIMARY KEY(run_id,sequence_number));
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

    @contextmanager
    def transaction(self):
        """Nested engine operations share one commit, including command + step."""
        if self.transaction_depth:
            yield
            return
        self.transaction_depth += 1
        try:
            with self.connection:
                yield
        finally:
            self.transaction_depth -= 1

    def append(self, events: list[WorldEvent], snapshot: WorldState | None = None) -> None:
        with self.transaction():
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
                        self.encode_payload(e.payload),
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
                        json.dumps(authoritative_state(snapshot)),
                        state_hash(snapshot),
                    ),
                )
                if snapshot.tick >= 1000 and snapshot.tick % 250 == 0:
                    self.compact(e.run_id, snapshot.tick - 250)

    def events(self, run_id: str, after: int = 0, limit: int = 1000) -> list[WorldEvent]:
        rows = self.connection.execute(
            "SELECT * FROM events WHERE run_id=? AND sequence_number>? "
            "ORDER BY sequence_number LIMIT ?",
            (run_id, after, limit),
        ).fetchall()
        return self.decode_rows(rows)

    def journal(self, run_id: str, after: int, through: int, limit: int = 1500):
        """Latest bounded human-facing history, with an explicit coverage watermark."""
        rows = self.connection.execute(
            "SELECT * FROM (SELECT * FROM events WHERE run_id=? AND sequence_number>? "
            "AND sequence_number<=? AND json_type(payload, '$.message') IS NOT NULL "
            "UNION ALL SELECT 'archive-' || run_id || '-' || sequence_number,run_id,"
            "sequence_number,tick,event_type,actor_id,payload,1 FROM history_journal "
            "WHERE run_id=? AND sequence_number>? AND sequence_number<=?) "
            "ORDER BY sequence_number DESC LIMIT ?",
            (run_id, after, through, run_id, after, through, limit),
        ).fetchall()
        return self.decode_rows(reversed(rows))

    @staticmethod
    def decode_rows(rows) -> list[WorldEvent]:
        return [
            WorldEvent(
                event_id=r[0],
                run_id=r[1],
                sequence_number=r[2],
                tick=r[3],
                event_type=r[4],
                actor_id=r[5],
                payload=EventStore.decode_payload(r[6]),
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
        has_history = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='history_metadata'"
        ).fetchone()
        archived = (
            has_history
            and self.connection.execute(
                "SELECT 1 FROM history_metadata WHERE run_id=?", (run_id,)
            ).fetchone()
        )
        if use_snapshot or archived:
            row = self.connection.execute(
                "SELECT sequence_number, state, state_hash FROM snapshots WHERE run_id=? "
                "ORDER BY sequence_number " + ("DESC" if use_snapshot else "ASC") + " LIMIT 1",
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

    @staticmethod
    def encode_payload(payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        if len(raw) < 16384:
            return raw
        packed = {"_genesis_zlib_v1": base64.b64encode(zlib.compress(raw.encode())).decode()}
        if "message" in payload:
            packed["message"] = payload["message"]
        return json.dumps(packed)

    @staticmethod
    def decode_payload(raw: str) -> dict:
        payload = json.loads(raw)
        if "_genesis_zlib_v1" in payload:
            return json.loads(zlib.decompress(base64.b64decode(payload["_genesis_zlib_v1"])))
        return payload

    def compact(self, run_id: str, before_tick: int) -> None:
        """Replace old after-images with counts, examples, and a replay checkpoint.

        Caller owns the transaction. The latest 250+ ticks remain replayable;
        historical replay starts at the oldest retained, hash-checked snapshot.
        """
        checkpoint = self.connection.execute(
            "SELECT sequence_number,tick,state_hash FROM snapshots WHERE run_id=? AND tick<=? "
            "ORDER BY sequence_number DESC LIMIT 1",
            (run_id, before_tick),
        ).fetchone()
        if not checkpoint:
            return
        sequence, tick, digest = checkpoint
        aggregates = {}
        journal = []
        total = 0
        for row in self.connection.execute(
            "SELECT * FROM events WHERE run_id=? AND sequence_number<=? ORDER BY sequence_number",
            (run_id, sequence),
        ):
            total += 1
            payload = self.decode_payload(row[6])
            action = str(payload.get("action", ""))
            key = (run_id, row[3] // 1000, row[4], row[5] or "", action)
            item = aggregates.setdefault(key, [0, row[3], row[3], []])
            item[0] += 1
            item[2] = row[3]
            if payload.get("message"):
                if len(item[3]) < 3:
                    item[3].append(
                        {"sequence": row[2], "tick": row[3], "message": payload["message"]}
                    )
                readable = {
                    k: payload[k] for k in ("message", "action", "peer_id", "goal") if k in payload
                }
                journal.append((run_id, row[2], row[3], row[4], row[5], json.dumps(readable)))
        for key, item in aggregates.items():
            self.connection.execute(
                "INSERT INTO history_aggregates VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(run_id,bucket,event_type,actor_id,action) DO UPDATE SET "
                "count=count+excluded.count,last_tick=excluded.last_tick",
                (*key, item[0], item[1], item[2], json.dumps(item[3])),
            )
        self.connection.executemany(
            "INSERT OR IGNORE INTO history_journal VALUES (?,?,?,?,?,?)", journal
        )
        self.connection.execute(
            "DELETE FROM history_journal WHERE run_id=? AND sequence_number NOT IN "
            "(SELECT sequence_number FROM history_journal WHERE run_id=? "
            "ORDER BY sequence_number DESC LIMIT 10000)",
            (run_id, run_id),
        )
        self.connection.execute(
            "INSERT INTO history_metadata VALUES (?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET "
            "through_sequence=excluded.through_sequence,through_tick=excluded.through_tick,"
            "state_hash=excluded.state_hash,original_events=original_events+excluded.original_events",
            (run_id, sequence, tick, digest, total),
        )
        self.connection.execute("DROP TRIGGER events_no_delete")
        self.connection.execute(
            "DELETE FROM events WHERE run_id=? AND sequence_number<=?", (run_id, sequence)
        )
        self.connection.execute(
            "CREATE TRIGGER events_no_delete BEFORE DELETE ON events "
            "BEGIN SELECT RAISE(ABORT, 'Event log is append-only'); END"
        )
        self.connection.execute(
            "DELETE FROM snapshots WHERE run_id=? AND sequence_number<?", (run_id, sequence)
        )

    def history(self, run_id: str) -> dict:
        metadata = self.connection.execute(
            "SELECT through_sequence,through_tick,original_events "
            "FROM history_metadata WHERE run_id=?",
            (run_id,),
        ).fetchone()
        counts = self.connection.execute(
            "SELECT event_type,action,SUM(count) FROM history_aggregates WHERE run_id=? "
            "GROUP BY event_type,action ORDER BY SUM(count) DESC",
            (run_id,),
        ).fetchall()
        recent = self.connection.execute(
            "SELECT tick,event_type,actor_id,payload FROM history_journal WHERE run_id=? "
            "ORDER BY sequence_number DESC LIMIT 100",
            (run_id,),
        ).fetchall()
        return {
            "compacted_through": metadata,
            "counts": counts,
            "recent": [
                {"tick": r[0], "event_type": r[1], "actor_id": r[2], **json.loads(r[3])}
                for r in recent
            ],
            "replay_note": (
                "Old per-tick states were aggregated; replay starts at the retained checkpoint."
            ),
        }

    def close(self) -> None:
        self.connection.close()
