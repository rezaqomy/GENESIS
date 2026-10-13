"""Verify a stored run without executing any policy."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.simulation.events.reducer import state_hash  # noqa: E402
from app.simulation.persistence.sqlite import EventStore  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run_id", nargs="?")
parser.add_argument(
    "--database", default=os.getenv("GENESIS_DB", "data/genesis.sqlite")
)
args = parser.parse_args()
store = EventStore(args.database)
try:
    run = args.run_id or store.latest_run()
    if not run:
        raise SystemExit("No recorded runs")
    # Pin one committed read view while a running server appends newer ticks.
    store.connection.execute("BEGIN")
    state = store.replay(run)
    snapshot_state = store.replay(run, use_snapshot=True)
    store.connection.commit()
    if state_hash(state) != state_hash(snapshot_state):
        raise SystemExit("Full-log and snapshot replay disagree")
    print(
        f"Run: {run}\nTick: {state.tick}\nSHA256: {state_hash(state)}\nReplay verified."
    )
finally:
    store.close()
