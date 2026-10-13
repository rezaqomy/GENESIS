# Genesis Phase 2 architecture

One Python writer owns integer positions, physiology, psychology, goals, inventories, settlements, construction and sparse world modifications. React only displays confirmed state and sends controls or read-only viewport requests. No LLM is required.

`WorldState → copied Observation → policy → proposed AgentIntent/Decision → validation → stable ordered resolution → mutation events → SQLite → WebSocket → PixiJS`

## Infinite terrain and lifecycle

Generator v2 maps absolute signed tile coordinates to coherent elevation/moisture/river noise, then resources. Chunk size is fixed at 32. Python floor division gives correct negative coordinates. The seed and generator version define base terrain; chunk creation order has no effect. A designed starter clearing provides a viable common camp without forcing later agent choices.

WorldAccess owns a bounded LRU base-chunk cache. Nearby observation queries activate required chunks. `active_radius` defines the agent-centered simulation interest set reported in instrumentation; static terrain needs no tick simulation. Resource regeneration is lazy everywhere: elapsed global regeneration boundaries are added to the last harvested quantity. A completed regeneration modification is pruned by the writer. Camera projections use an entirely separate visual LRU cache; no policy sees camera state. There is no inactive agent simulation: all persistent living agents remain active wherever they travel. Persistent buildings receive cheap deterministic maintenance/farm/fuel updates regardless of camera or chunk activation.

Generated tiles/resources are excluded from snapshots and canonical hashes. Sparse terrain overrides and resource quantities/harvest ticks, buildings, settlements and agent knowledge remain authoritative. Unloading a base chunk loses no modifications. WorldAccess reconstructs collision including completed walls/towers/bridges. Navigation uses a bounded coarse chunk corridor and local A* against observed terrain, recalculated each decision. Exploration excludes a short recent trail to escape repeated frontiers along long obstacles. Coarse plans are intentions, not knowledge of unseen terrain.

## Cognition and settlement modules

Seeded personality traits are stable normalized values. Psychology changes from local warmth/protection, compatible companions, actual relationships, crowding, exposure and time away. A spatial bucket index bounds companion queries. Per-agent knowledge retains 128 recent chunks, 48 discoveries, 16 food observations and 12 recent movement positions; the world retains 1,024 explored chunk keys for the minimap. Eviction forgets knowledge, not persistent physical changes.

UtilityPolicy scores need, trait, reward, travel, risk, social and scarcity factors. Run configuration records weights. Invalid goals expose reasons. Goals commit for six ticks with .09 switching hysteresis; urgent hunger/exhaustion overrides it. Repeated rejected actions release commitment and cool the failed goal down. Exploration budgets increase with independence. Resupply, danger, loneliness and cargo motivate return. Policies receive copied observations and public settlement project/status facts, never unrestricted mutable state.

Construction validation owns material availability, physical access, recipes, energy, tile suitability, capacity and occupied sites. Materials come from inventory plus a nearby communal cache. Distant projects require physical withdrawal/hauling of their materials. Four build actions complete a structure; only creation charges materials. Building effects depend on completed, durable structures and distance. Conditional remote-camp migration updates membership and home; it is not an identity-based assigned role.

## Writer, replay and compatibility

One asyncio task processes FIFO controls and synchronously executes ticks without awaits/mutations from other tasks. Stable lexicographic actor order resolves resource/tile conflicts. Speed changes wall-clock pacing only. A database file lock prevents independent writer instances. Restart restores committed state and records a pause.

WORLD_CREATED records configuration and initial authoritative state. COMMAND_ACCEPTED records controls. Agent after-images carry traits/psychology/decisions/knowledge. RESOURCE_MODIFIED/RESTORED, TERRAIN_MODIFIED, BUILDING_UPDATED, SETTLEMENT_UPDATED and WORLD_METADATA supply the remaining mutations. Each TICK_COMPLETED stores canonical SHA256. Replay reduces events without policies or random draws; generated terrain remains reconstructible from seed/version. Transactions atomically append a tick and optional snapshot every 25 ticks. Append-only triggers reject updates/deletes. Full and snapshot replay verify hashes. UUIDs, caches, camera state and performance timings do not enter the hash.

Finite Phase 1 runs use RulePolicy/BFS and the original canonical field set so old hashes remain valid. Config.infinite defaults false in the domain; the app defaults true. Upgrading a restored finite run starts a new infinite run, preserving archived logs.

## Streaming and rendering

An initial snapshot contains full authoritative entities/metadata and recent readable events. Subsequent `entities` packets contain authoritative after-images with no generated chunks. Updates include only the new readable events; persisted intent/state payloads stay in SQLite and the archive API instead of being repeated in the live journal. The queue retains only the latest state, so missed updates recover without applying fragile deltas. Read-only viewport requests (max25 chunks) receive separate compact terrain/walkability/resource messages. Per-connection send locking serializes replies and updates. Chunk packets carry run/sequence IDs; frontend rejects other runs and stale entity sequences. Reconnection sends a snapshot and re-requests the viewport.

The frontend retains 48 chunk projections. Pixi culls chunk nodes/resources/humans outside the viewport and retains sprites between entity updates. Backend coordinates map to 32-pixel tiles; interpolation affects visualization only. Pause/reset/reconnect resynchronize positions. Camera smoothing, follow, settlement/explorer jumps and explored-region minimap have no simulation effect. Local original PNGs load through a manifest with nearest filtering and explicit missing-asset fallbacks. Day/night/weather, water, tree sway, construction/gathering effects and warm firelight are lightweight configurable visual effects.

## Performance and limits

Tick and decision durations, active/base/visual-cache chunk counts and JSON payload size are non-authoritative service metrics. The frontend measures FPS and rendered chunks. Ten agents are supported; full entity after-images and synchronous SQLite need future benchmarking before claiming 100-agent throughput. Resource depletion and construction are real; survival is not guaranteed. This is a local sandbox without authentication, distant omniscient navigation, combat, dialogue or multi-settlement politics.
