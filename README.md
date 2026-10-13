# Genesis

A persistent artificial world with ten autonomous inhabitants. Python owns the simulation; a React/PixiJS observatory lets you watch it unfold, inspect individuals, and control time. Phase 2 adds signed procedural chunks, individual personalities, explained utility decisions, functional settlements and original pixel art. There is no LLM inference.

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
.venv/bin/python scripts/verify_experiment.py --ticks 700  # actual utility/settlement/replay probe
```

`make replay` defaults to `data/genesis.sqlite`; set GENESIS_DB or use `scripts/replay.py --database ...` for a different database. Replay is safe while the running application appends committed transactions, though pause first to compare a stable API hash.

## Docker

```sh
docker compose up --build
# or: make docker
```

Open http://localhost:5173. SQLite persists in the `genesis-data` named volume. `docker compose down` stops the app and retains data. The Compose frontend runs Vite for this local development MVP and proxies HTTP/WS to the backend container. A production UI bundle is available with `make build`; deploying it requires a reverse proxy for `/api`, `/health`, and `/ws` to the single backend process.

## Explore

- Scroll to zoom; drag to pan. **Center** preserves zoom; **Fit world** frames the starting settlement. **Follow agent** tracks the selection; **Find explorer** locates the inhabitant farthest from home. Click the minimap to travel across known regions.
- Click a human character or their name in the inhabitants list to open their inspector.
- Health and energy are 0–100. **High hunger means hungry**; 100 means starving.
- Pause/resume, advance a single tick while paused, or select a pacing multiplier.
- Enter an integer seed and reset to regenerate a reproducible world.
- The world journal streams actual resolved actions and controls. Filter by action/event or agent. **Hold** freezes the displayed cursor while the simulation continues.
- Inspector tabs show real physiology/psychology, personality, decision scores/factors/rejections, inventory/tools, companions and event history.
- The settlement panel shows shared reserves, completed structures, local safety/comfort, crowding and exploration activity. Members can be clicked to select and focus them.
- Optional atmospheric effects show deterministic day/night and weather. Expand Performance for measured tick/decision time, payload bytes, cached/active/visible chunks and FPS.

## API

GET `/health`, `/api/world`, `/api/agents`, `/api/agents/{id}`, `/api/events`.
POST `/api/simulation/start`, `/pause`, `/resume`, `/step`, `/reset`, `/speed` (all under `/api/simulation`). Reset body: `{"seed":42}`. Speed body: `{"multiplier":2}`. Invalid bodies return 422; stepping while running returns 409.
WS `/ws/simulation` sends a `snapshot` on connection and `entities` updates for infinite runs, with per-run event sequence, state hash and recent events. Terrain is streamed separately: send `{"type":"viewport","chunks":[[-1,0],[0,0]]}` (at most 25 signed coordinates). A `chunks` response contains compact terrain/walkability strings and resource projections. Send `resync` for another snapshot. Camera requests never discover terrain for agents or change simulation outcomes. Reconnection never creates a second simulation.
GET `/api/chunks/{cx}/{cy}` returns a typed chunk projection; `/api/settlements` returns live settlement state.
GET `/api/replay/{run_id}` reconstructs the recorded world and returns its hash without rerunning policies. `/api/events?run_id=...&after=0&limit=500` retrieves archived event pages; use the returned `next_sequence` as the next `after` cursor.

## Engineering notes

See [architecture](docs/architecture.md), [simulation rules](docs/simulation-rules.md), and [future cognition integration](docs/future-ai-integration.md). Domain modules separate perception, policies, pathfinding, validation, action resolution, mutation events and persistence. Fixed ticks and stable actor/resource ordering make results independent of rendering speed. SQLite records the generated state, all accepted commands, complete mutation events, tick hashes and periodic snapshots. Full-log and snapshot replay reconstruct the same authoritative state.

The 60 local assets were created through Figma AI and processed into PNG terrain, nature/building sprites, items and four directional character sheets. Action poses were assembled from generated walk bases and tools. See [asset manifest](docs/asset-generation-manifest.md) for source batches, exact prompts, filenames and replacements. `python3 scripts/build_assets.py` rebuilds assets from retained sources (requires Pillow). Nearest-neighbor rendering preserves pixels. Missing textures use an explicit procedural fallback, counted in Performance; no external service is needed at runtime.

World generation v2 uses coherent absolute-coordinate noise and 32×32 chunks. Cache eviction is safe: only resource/terrain modifications and persistent entities are stored. Inactive resources recover on global tick boundaries, computed lazily, without simulating unseen chunks. An agent observes local terrain (8 tiles, 12 near towers), keeps bounded knowledge, and chooses among 15 explained goals with commitment and recovery cooldowns. Settlements have costs: finite stores, competing agents, depletion, crowding, fuel and maintenance. Survival and migration are conditional, not guaranteed.

The application defaults to infinite mode. Set `GENESIS_INFINITE=0` for legacy finite runs. Existing Phase 1 event logs retain their original hashes; enabling chunks on a finite save starts a new run and keeps old logs for replay. Domain configuration defaults remain finite for compatibility. `GENESIS_ACTIVE_RADIUS` (0–2) and `GENESIS_CACHE_SIZE` (16–256) configure chunk interest/cache limits. Utility weights are normalized configuration values stored in each run; optional `GENESIS_UTILITY_WEIGHTS` is a JSON object, e.g. `{"trait":0.35,"risk":0.30}`. A restored run keeps its recorded weights. Change weights with a fresh database for a reproducible experiment.

This is a local experimental MVP without authentication. Agent and discovery caches are bounded; sparse persistent construction may grow as the experiment creates structures. Entity after-images prioritize correct resynchronization at 10-agent scale. Coarse navigation is a bounded chunk corridor with local A* replanning, not a precomputed map of distant obstacles. Relationships model proximity/compatibility; there is no dialogue, trade or combat.

## Browser verification

The browser test uses its own backend/database and frontend on ports 8001/5174, leaving the main application on 8000/5173 available:

```sh
cd frontend && npx playwright install chromium && cd ..
make e2e
```

It verifies autonomous changes, pause/step, selection through Pixi hit testing, personality/decision tabs, minimap/follow, camera controls, network reconnect, survival actions, replay hashes, journal filters, seed reset and responsive layout. Screenshots are saved under `artifacts/`. Chromium's software WebGL is enabled for headless verification; an interactive browser needs WebGL support. Each browser run uses a fresh isolated database, leaving the running development world untouched.
