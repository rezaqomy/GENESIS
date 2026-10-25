import sys
import sqlite3
import json
import collections
import time
import os
import argparse
import fcntl
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.simulation.persistence.sqlite import EventStore  # noqa: E402
from app.simulation.events.reducer import (  # noqa: E402
    WorldEvent,
    authoritative_state,
    state_hash,
)

parser = argparse.ArgumentParser(
    description="Offline history aggregation; creates a verified separate database."
)
parser.add_argument("source")
parser.add_argument("output")
args = parser.parse_args()
source = args.source
lock = open(source + ".lock", "a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
old = sqlite3.connect("file:" + os.path.abspath(source) + "?mode=ro", uri=True)
old.execute("pragma temp_store=MEMORY")
if old.execute("SELECT 1 FROM sqlite_master WHERE name='history_metadata'").fetchone():
    if old.execute("SELECT 1 FROM history_metadata LIMIT 1").fetchone():
        raise ValueError(
            "Source is already aggregated; use automatic retention instead"
        )
runs = [r[0] for r in old.execute("select distinct run_id from snapshots")]
reader = object.__new__(EventStore)
reader.connection = old
reader.transaction_depth = 0
latest = reader.latest_run()
runs.sort(key=lambda run: run == latest)
staged = args.output
if os.path.exists(staged):
    raise ValueError("Output already exists")
new = EventStore(staged)

worlds = {}
for run in runs:
    w = reader.replay(run, use_snapshot=True)
    seq = reader.sequence(run)
    worlds[run] = (w, seq)
    new.append(
        [
            WorldEvent(
                run_id=run,
                sequence_number=seq,
                tick=w.tick,
                event_type="WORLD_CREATED",
                payload={"state": authoritative_state(w)},
            )
        ],
        w,
    )
    print("checkpoint", run, w.tick, seq, state_hash(w), flush=True)
counts = {}
journals = {r: collections.deque(maxlen=10000) for r in runs}
total = 0
start = time.time()
for run, seq, tick, kind, actor, payload in old.execute(
    "select run_id,sequence_number,tick,event_type,actor_id,payload from events order by rowid"
):
    action = ""
    msg = None
    detail = {}
    if kind not in (
        "AGENT_UPDATED",
        "TICK_COMPLETED",
        "ECOSYSTEM_UPDATED",
        "SETTLEMENT_UPDATED",
        "BUILDING_UPDATED",
        "RESOURCE_UPDATED",
        "WORLD_CREATED",
        "COGNITION_CONSUMED",
    ):
        detail = EventStore.decode_payload(payload)
        action = str(detail.get("action", ""))
        msg = detail.get("message")
    key = (run, tick // 1000, kind, actor or "", action)
    if key not in counts:
        counts[key] = [0, tick, tick, []]
    v = counts[key]
    v[0] += 1
    v[2] = tick
    if msg:
        sample = {"sequence": seq, "tick": tick, "message": msg}
        if len(v[3]) < 3:
            v[3].append(sample)
        journals[run].append(
            (
                run,
                seq,
                tick,
                kind,
                actor,
                json.dumps(
                    {
                        k: detail[k]
                        for k in ("message", "action", "peer_id", "goal")
                        if k in detail
                    },
                    ensure_ascii=False,
                ),
            )
        )
    total += 1
    if total % 100000 == 0:
        print("scanned", total, "seconds", round(time.time() - start), flush=True)
new.connection.executemany(
    "insert into history_aggregates values (?,?,?,?,?,?,?,?,?)",
    (
        (*k, v[0], v[1], v[2], json.dumps(v[3], ensure_ascii=False))
        for k, v in counts.items()
    ),
)
for run, (world, seq) in worlds.items():
    n = sum(v[0] for k, v in counts.items() if k[0] == run)
    new.connection.execute(
        "insert into history_metadata values (?,?,?,?,?)",
        (run, seq, world.tick, state_hash(world), n),
    )
    new.connection.executemany(
        "insert into history_journal values (?,?,?,?,?,?)", journals[run]
    )
new.connection.commit()
for run, (world, seq) in worlds.items():
    assert state_hash(new.replay(run)) == state_hash(world)
    assert new.sequence(run) == seq
assert new.connection.execute("pragma integrity_check").fetchone()[0] == "ok"
new.connection.execute("pragma wal_checkpoint(TRUNCATE)")
new.close()
old.close()
with open(staged + ".report.json", "w") as f:
    json.dump(
        {
            "original_bytes": os.path.getsize(source),
            "events": total,
            "compact_bytes": os.path.getsize(staged),
            "runs": {
                r: {"tick": w.tick, "sequence": s, "hash": state_hash(w)}
                for r, (w, s) in worlds.items()
            },
        },
        f,
        indent=2,
    )
print("VERIFIED", open(staged + ".report.json").read(), flush=True)
