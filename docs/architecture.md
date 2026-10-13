# Genesis architecture

Genesis has one authoritative world per process/database. Python 3.12 owns integer tile positions, drives, inventories, resources and clock controls. React only sends commands and displays confirmed state. There is no LLM inference.

The pipeline is `WorldState → Observation → AgentPolicy → AgentIntent → validator → resolver → mutation events → SQLite → WebSocket → PixiJS`.

- `simulation/models`: strict Pydantic v2 domain types.
- `simulation/engine`: seeded generation and synchronous fixed-step state transitions.
- `simulation/observation`: copied local perception, with Manhattan sight radius 8.
- `simulation/policies`: the small policy protocol and deterministic rule policy.
- `simulation/pathfinding`: BFS with a fixed north/east/south/west neighbor order.
- `simulation/actions`: preconditions, deterministic action resolution and physiology.
- `simulation/events`: versioned events, pure state reducer and canonical SHA256 hashing.
- `simulation/persistence`: append-only SQLite log and periodic snapshots.
- `services/simulation`: asyncio pacing, FIFO command queue and subscriber queues.
- `api`: request and response contracts. FastAPI lifespan starts and stops the writer.
- `frontend/src/game`: procedural terrain/characters, camera and movement interpolation.

## Writer and clock

One service task applies commands in FIFO arrival order. Every tick synchronously advances physiology, freezes observations, calls policies, validates and resolves intents in lexicographic agent ID order, regenerates resources, logs mutations, advances tick and publishes. No awaits occur inside a state transition. Commands can also be processed while paused. Step is accepted only when paused. Start/resume is idempotent. Speed changes only wall-clock pacing; each tick uses identical integer rules. The base interval is 500 ms plus computation time; the clock never skips simulation ticks to catch up with rendering.

A POSIX advisory file lock rejects a second server owning the same database. Use one Uvicorn worker. HTTP and all WebSocket clients share the same service. A restart restores the latest run and records a pause command, preserving a reviewable state rather than advancing while nobody is watching.

## Event sourcing

WORLD_CREATED records the complete generated state, configuration and seed. COMMAND_ACCEPTED records controls and resulting clock values. Every tick records ACTION_RESOLVED/REJECTED for analysis, AGENT_UPDATED for every agent, RESOURCE_UPDATED for changed resources, AGENT_DIED, and TICK_COMPLETED with a canonical state hash. These after-image mutation events are sufficient to reconstruct state without policies, generation or random draws. Event UUIDs/run IDs are metadata and are excluded from the state hash.

Each tick's events and optional snapshot commit in one SQLite transaction. Sequence numbers are unique per run; the log has triggers rejecting UPDATE/DELETE. Snapshots every 25 ticks (and at creation) contain state plus hash and a sequence cursor. Replay from the full log validates each completed tick hash; snapshot replay validates the snapshot then subsequent tick hashes. Reset creates a new run, preserving old runs. Both modes must give the same final hash.

## Transport

GET `/api/world` and WS `/ws/simulation` share a typed full snapshot: run ID, event sequence, tick interval, state, hash and up to 250 recent readable events. Every subsequent WS message is a complete state, intentionally favoring reliable resynchronization over premature delta complexity for 1,200 tiles and ten agents. Queue capacity is one: slow clients discard an obsolete update and receive the latest full state. `/api/events?run_id=...&after=...&limit=...` provides archival sequence pagination.

The browser reconnects with bounded exponential backoff and rejects older sequence numbers for the same run. It keeps up to 1,500 journal events in memory. Reconnection supplies recent events; older history is available through the archive API. A client WS text message requests another snapshot. Clients cannot send intents or mutate state over WS.

## Rendering

Integer positions are projected to 24-pixel tiles. Confirmed moves interpolate from the current rendered position to the new target over one tick interval; resets snap and rebuild the scene, pause snaps to confirmed positions, and single-step animates a confirmed move. Graphics, labels and animation have no simulation effect. Original procedural graphics require no external art assets. Mouse wheel zoom preserves the cursor's world position; drag pans; center and fit controls restore the view.

## Scope and limits

Local experimental application, without authentication or multi-user permissions. Full-state messages and synchronous SQLite/BFS are appropriate at Phase 1 scale, not a claim of large-scale throughput. A persistence error stops the writer and health reports unavailable; restart recovers the last committed state. No trades, conversations, relationships, beliefs or hidden LLM decisions are simulated.
