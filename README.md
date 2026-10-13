# Genesis

A persistent artificial world with ten autonomous inhabitants. Python owns the simulation; a React/PixiJS observatory lets you watch it unfold, inspect individuals, and control time. Phase 1 uses deterministic local rule policies, with no LLM inference.

## Run locally

Requires **Python 3.12+**, **Node 22+**, npm, and a POSIX environment (Linux/macOS). From this repository:

```sh
make dev
```

This installs the Python virtual environment and locked frontend dependencies on first run, then starts both servers. Open **http://localhost:5173**. API documentation: http://localhost:8000/docs. The world starts paused; click **Start world**. Ctrl+C stops both processes.

Optional: copy `.env.example` to `.env` before startup. The default seed is 42; SQLite is stored in `data/genesis.sqlite`. A restart restores the latest committed run and pauses it. Reset creates a new run; previous logs remain replayable. Run only **one backend worker** against a database; a file lock enforces ownership.

```sh
make install      # install dependencies only
make test         # backend tests
make lint         # Ruff, formatting, ESLint
make typecheck    # strict TypeScript
make build        # production frontend bundle
make check        # all of the above verification
make replay       # replay and hash-check latest stored run without policies
make replay RUN=<run-id>
```

`make replay` defaults to `data/genesis.sqlite`; set GENESIS_DB or use `scripts/replay.py --database ...` for a different database. Replay is safe while the running application appends committed transactions, though pause first to compare a stable API hash.

## Docker

```sh
docker compose up --build
# or: make docker
```

Open http://localhost:5173. SQLite persists in the `genesis-data` named volume. `docker compose down` stops the app and retains data. The Compose frontend runs Vite for this local development MVP and proxies HTTP/WS to the backend container. A production UI bundle is available with `make build`; deploying it requires a reverse proxy for `/api`, `/health`, and `/ws` to the single backend process.

## Explore

- Scroll to zoom; drag to pan. **Center** preserves zoom; **Fit world** fits the whole map.
- Click a human character or their name in the inhabitants list to open their inspector.
- Health and energy are 0–100. **High hunger means hungry**; 100 means starving.
- Pause/resume, advance a single tick while paused, or select a pacing multiplier.
- Enter an integer seed and reset to regenerate a reproducible world.
- The world journal streams actual resolved actions and controls. Filter by action/event or agent. **Hold** freezes the displayed cursor while the simulation continues.
- The inspector highlights a confirmed destination tile and shows inventory, drives, position and recent activity.

## API

GET `/health`, `/api/world`, `/api/agents`, `/api/agents/{id}`, `/api/events`.
POST `/api/simulation/start`, `/pause`, `/resume`, `/step`, `/reset`, `/speed` (all under `/api/simulation`). Reset body: `{"seed":42}`. Speed body: `{"multiplier":2}`. Invalid bodies return 422; stepping while running returns 409.
WS `/ws/simulation` sends a full authoritative state on connection and after updates, with per-run event sequence and recent events. Any text message requests resynchronization. Reconnection never creates a second simulation.
GET `/api/replay/{run_id}` reconstructs the recorded world and returns its hash without rerunning policies. `/api/events?run_id=...&after=0&limit=500` retrieves archived event pages; use the returned `next_sequence` as the next `after` cursor.

## Engineering notes

See [architecture](docs/architecture.md), [simulation rules](docs/simulation-rules.md), and [future cognition integration](docs/future-ai-integration.md). Domain modules separate perception, policies, pathfinding, validation, action resolution, mutation events and persistence. Fixed ticks and stable actor/resource ordering make results independent of rendering speed. SQLite records the generated state, all accepted commands, complete mutation events, tick hashes and periodic snapshots. Full-log and snapshot replay reconstruct the same authoritative state.

The characters, terrain, trees, bushes, rocks and motion are original procedural Pixi graphics. No paid or remote art assets, mocked movement, external services, Redis or LLMs are required. This is a local experimental MVP, without authentication. Synchronous policies and complete snapshots prioritize clarity and correctness at Phase 1 scale.

## Browser verification

The browser test uses its own backend/database and frontend on ports 8001/5174, leaving the main application on 8000/5173 available:

```sh
cd frontend && npx playwright install chromium && cd ..
make e2e
```

It verifies autonomous changes, pause/step, selection through Pixi hit testing, camera controls, network reconnect, all four active survival actions, replay hashes, journal filters, seed reset and responsive layout. Screenshots are saved under `artifacts/`. Chromium's software WebGL is enabled for headless verification; an interactive browser needs WebGL support. The test resets its isolated database, not the running development world.
