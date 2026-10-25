# Genesis

A persistent artificial world with ten autonomous inhabitants. Python owns the simulation; a React/PixiJS observatory lets you watch it unfold, inspect individuals, and control time. Phase 2 adds signed procedural chunks, individual personalities, explained utility decisions, functional settlements and original pixel art. Local CPU cognition uses the Laya decision model, with persistent experience memory and a separate local model for generated conversations.

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

## Local models and agent memory

`make dev` installs an isolated CPU Laya runtime and starts its decision service on port 11437. It downloads the pinned [official multilingual Laya checkpoint](https://huggingface.co/convaiinnovations/laya-multilingual) on first use. Laya is the default decision provider (`GENESIS_DECISION_PROVIDER=laya`); it answers typed choices without generating text. Goal selection runs in bounded batches, with cached goals directing actions between refreshes. [Setup details](docs/future-ai-integration.md).

Ollama remains optional: set `GENESIS_DECISION_PROVIDER=ollama` and choose `qwen2.5:0.5b` or `llama3.2:1b` with `GENESIS_LOCAL_MODEL`. `GENESIS_COGNITION=0` runs without inference.

Agents retain short-term experiences, important long-term episodes, timestamped food observations and context-specific practical lessons. Actual action outcomes influence goal scores; memory retrieval uses relevance, importance and recency. The legacy 48-experience journal remains readable. See [memory research and design](docs/agent-memory-research.fa.md) and [measured behavior comparison](docs/memory-evaluation.md). Inspect **Memory** and **Decision** to see experiences and model thoughts. Emergency survival keeps deterministic priority; slow or invalid inference uses the existing utility policy. `/api/cognition` reports live inference status. Replay retains model decisions and memory without calling a model again.

The example configuration enables local conversations with `GENESIS_DIALOGUE_PROVIDER=ollama`, `GENESIS_DIALOGUE_URL=http://localhost:11435/v1` and `GENESIS_DIALOGUE_MODEL=llama3.2:1b`. Pull that model with `OLLAMA_HOST=127.0.0.1:11435 ollama pull llama3.2:1b` after starting the local server. `scripts/dev.sh` starts the isolated Ollama server when needed. For another compatible endpoint, set `GENESIS_DIALOGUE_PROVIDER=compatible`, its `/v1` URL, model and optional `GENESIS_DIALOGUE_API_KEY`.

Nearby agents generate short English utterances from their own memories and recent exchanges. Both remember accepted messages; replies are independent of Laya goal refreshes. One dialogue job runs at a time, with a 12-tick cooldown per speaker. Leaving hearing range, stale messages and survival emergencies prevent delivery. Use **World Journal → DIALOGUE** to read conversations. Spoken claims are memories, not automatically verified recipes or map facts. See [dialogue behavior and validation (Persian)](docs/dialogue.fa.md).

For OpenRouter conversations, set `GENESIS_DIALOGUE_PROVIDER=compatible`,
`GENESIS_DIALOGUE_URL=https://openrouter.ai/api/v1`, and
`GENESIS_DIALOGUE_MODEL=minimax/minimax-m3.1-flash:free`. Store
`GENESIS_DIALOGUE_API_KEY` only in the ignored local `.env` file. Set
`GENESIS_DIALOGUE_PROACTIVE=1` to let adjacent agents initiate conversations even
while pursuing other goals, provided hunger is below 65 and energy above 25.
Survival guards still control delivery. For this free endpoint, suggested settings
are `GENESIS_DIALOGUE_COOLDOWN=8` ticks, `GENESIS_DIALOGUE_MIN_INTERVAL=6` seconds
globally and `GENESIS_DIALOGUE_SPEAKER_INTERVAL=30` seconds per speaker. Requests
remain serialized, with backoff after HTTP errors, including rate limits. Daily
provider quotas can still stop conversation generation. `/api/cognition` exposes
the dialogue model, counters and retry delay, never the API key. Speech proposals
do not automatically execute trades, transfers or other social actions.

## Community cooperation

Agents can post local public construction projects, pool their materials, give spare
meals to needy neighbours, and repair standing structures. Food production and
maintenance compete with private goals, with emergency survival taking priority.
The settlement's **Working together** section shows the current project and actual
contributions to food supply, materials, construction, irrigation and care. These
are observed activities, not assigned professions. Public notices remain local to
the meeting place; speech alone does not execute an agreement. See
[community mechanics and evaluation](docs/community-cooperation.fa.md).

## Docker

```sh
docker compose up --build
# or: make docker
```

For CPU Laya cognition in Docker, run `GENESIS_COGNITION=1 docker compose --profile cognition up --build`. Its checkpoint downloads automatically into `genesis-laya`. For optional Ollama decisions, set `GENESIS_DECISION_PROVIDER=ollama` and pull the chosen model with `docker compose --profile cognition exec ollama ollama pull qwen2.5:0.5b`. Without this profile, set `GENESIS_COGNITION=0` if your `.env` enables cognition.

Open http://localhost:5173. SQLite persists in the `genesis-data` named volume. `docker compose down` stops the app and retains data. The Compose frontend runs Vite for this local development MVP and proxies HTTP/WS to the backend container. A production UI bundle is available with `make build`; deploying it requires a reverse proxy for `/api`, `/health`, and `/ws` to the single backend process.

## Explore

- Scroll to zoom; drag to pan. **Center** preserves zoom; **Fit world** frames the starting settlement. **Follow agent** tracks the selection; **Find explorer** locates the inhabitant farthest from home. Click the minimap to travel across known regions.
- Click a human character or their name in the inhabitants list to open their inspector.
- Health and energy are 0–100. **High hunger means hungry**; 100 means starving.
- Pause/resume, advance a single tick while paused, or select a pacing multiplier.
- Enter an integer seed and reset to regenerate a reproducible world.
- The world journal streams actual resolved actions and controls. Filter by action/event or agent. **Hold** freezes the displayed cursor while the simulation continues.
- Inspector tabs show real physiology/psychology, personality, decision scores/factors/rejections, inventory/tools, companions and event history.
- **Memory** shows bounded short/long-term memories and practical lessons. **Plans** shows multi-stage food, construction and expedition tasks, measured outcomes and verified strategies. Emergency survival can interrupt a plan; agents reserve next movement tiles and replan or yield on conflicts.
- The settlement panel shows shared reserves, completed structures, local safety/comfort, crowding and exploration activity. Members can be clicked to select and focus them.
- Optional atmospheric effects show deterministic day/night and weather. Expand Performance for measured tick/decision time, payload bytes, cached/active/visible chunks and FPS.

## API

GET `/health`, `/api/world`, `/api/agents`, `/api/agents/{id}`, `/api/events`.
POST `/api/simulation/start`, `/pause`, `/resume`, `/step`, `/reset`, `/speed` (all under `/api/simulation`). Reset body: `{"seed":42}`. Speed body: `{"multiplier":2}`. Invalid bodies return 422; stepping while running returns 409.
WS `/ws/simulation` sends a `snapshot` on connection and `entities` updates for infinite runs, with per-run event sequence, state hash and recent events. Terrain is streamed separately: send `{"type":"viewport","chunks":[[-1,0],[0,0]]}` (at most 25 signed coordinates). A `chunks` response contains compact terrain/walkability strings and resource projections. Send `resync` for another snapshot. Camera requests never discover terrain for agents or change simulation outcomes. Reconnection never creates a second simulation.
GET `/api/chunks/{cx}/{cy}` returns a typed chunk projection; `/api/settlements` returns live settlement state.
GET `/api/replay/{run_id}` reconstructs the recorded world and returns its hash without rerunning policies. `/api/events?run_id=...&after=0&limit=500` retrieves archived event pages; use the returned `next_sequence` as the next `after` cursor.

## Engineering notes

See [architecture](docs/architecture.md), [simulation rules](docs/simulation-rules.md), and [cognition integration](docs/future-ai-integration.md). Domain modules separate perception, policies, pathfinding, validation, action resolution, mutation events and persistence. Fixed ticks and stable actor/resource ordering make results independent of rendering speed. SQLite records the generated state, all accepted commands, complete mutation events, tick hashes and periodic snapshots. Full-log and snapshot replay reconstruct the same authoritative state.

See [similar projects and implemented adaptations (Persian)](docs/similar-projects.fa.md) and [measured behavior comparison](docs/planning-evaluation.fa.md). Strategy learning uses verified fixed recipes; it does not generate new executable skills.

The [extended game AI research (Persian)](docs/game-ai-deep-research.fa.md) compares life simulations, social games, traditional NPC architectures and research agents against the current code. It includes a [source catalog with reading limits](docs/research/game-ai-sources.fa.md) and a [proposed development and evaluation roadmap](docs/agent-development-roadmap.fa.md). These are research proposals, not additional implemented features. The existing 240-tick behavior comparison covers one simulated day.

The [project audit (Persian)](docs/project-audit.fa.md) records the original scheduling, persistence, cognition and UI findings. The [implemented fixes and regression coverage](docs/audit-fixes.fa.md) include independent tick scheduling, transactional state rollback, separate dialogue jobs, energy-aware actions, reconstruction of destroyed buildings and journal recovery with a stable Hold view. Run `.venv/bin/python scripts/audit_project.py` to probe the current behavior without opening the application's database.

The 60 local assets were created through Figma AI and processed into PNG terrain, nature/building sprites, items and four directional character sheets. Action poses were assembled from generated walk bases and tools. See [asset manifest](docs/asset-generation-manifest.md) for source batches, exact prompts, filenames and replacements. `python3 scripts/build_assets.py` rebuilds assets from retained sources (requires Pillow). Nearest-neighbor rendering preserves pixels. Missing textures use an explicit procedural fallback, counted in Performance; no external service is needed at runtime.

World generation v2 uses coherent absolute-coordinate noise and 32×32 chunks. Cache eviction is safe: only resource/terrain modifications and persistent entities are stored. Inactive resources recover on global tick boundaries, computed lazily, without simulating unseen chunks. An agent observes local terrain (8 tiles, 12 near towers), keeps bounded knowledge, and chooses among 15 explained goals with commitment and recovery cooldowns. Settlements have costs: finite stores, competing agents, depletion, crowding, fuel and maintenance. Survival and migration are conditional, not guaranteed.

The application defaults to infinite mode. Set `GENESIS_INFINITE=0` for legacy finite runs. Existing Phase 1 event logs retain their original hashes; enabling chunks on a finite save starts a new run and keeps old logs for replay. Domain configuration defaults remain finite for compatibility. `GENESIS_ACTIVE_RADIUS` (0–2) and `GENESIS_CACHE_SIZE` (16–256) configure chunk interest/cache limits. Utility weights are normalized configuration values stored in each run; optional `GENESIS_UTILITY_WEIGHTS` is a JSON object, e.g. `{"trait":0.35,"risk":0.30}`. A restored run keeps its recorded weights. Change weights with a fresh database for a reproducible experiment.

This is a local experimental MVP without authentication. Agent and discovery caches are bounded; sparse persistent construction may grow as the experiment creates structures. Entity after-images prioritize correct resynchronization at 10-agent scale. Coarse navigation is a bounded chunk corridor with local A* replanning, not a precomputed map of distant obstacles. Relationships model proximity/compatibility and validated conversations; trade and combat remain outside this MVP.

## Browser verification

The browser test uses its own backend/database and frontend on ports 8001/5174, leaving the main application on 8000/5173 available:

```sh
cd frontend && npx playwright install chromium && cd ..
make e2e
```

It verifies autonomous changes, pause/step, selection through Pixi hit testing, personality/decision tabs, minimap/follow, camera controls, network reconnect, survival actions, replay hashes, journal filters, seed reset and responsive layout. Screenshots are saved under `artifacts/`. Chromium's software WebGL is enabled for headless verification; an interactive browser needs WebGL support. Each browser run uses a fresh isolated database, leaving the running development world untouched.

Minecraft-inspired expansion: [scope and current mechanics (Persian)](docs/minecraft-scope.fa.md).
Modern worlds support local `DIG`, `MINE`, and `PLACE_BLOCK` terrain work with conserved
materials, tested mining tools, collision updates, and replayable terrain events.
This is an initial 2D foundation; it does not implement Minecraft feature parity.

The [creative workshop (Persian)](docs/creative-workshop.fa.md) adds physical assembly
hypotheses from conversation or empirical search, paid trials, device fabrication,
finite fishing, water collection, cultivation, heating/smelting/cooking, salvage,
and two-party barter. Inspect an agent's Building tab for proposals and measured outcomes.

### Living systems

The 2D world now includes seed crops with moisture and daylight growth, finite wildlife, feeding/taming/breeding, animal produce, adjacent combat, theft with relationship consequences, and recoverable belongings after death. Agents consider these through local utility goals and model context; automatic use of every capability is not guaranteed. This is not Minecraft feature parity. See [rules and limitations (Persian)](docs/living-world.fa.md) and [scope](docs/minecraft-scope.fa.md). Run `PYTHONPATH=backend .venv/bin/python scripts/evaluate_ecosystem.py --ticks 1200 --seed 42` for an isolated autonomous evaluation.
