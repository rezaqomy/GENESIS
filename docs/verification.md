# Phase 1 verification

Executed on 13 October 2026, Python 3.12.3 and Node 22.22.2.

- Milestone 1: foundation pytest suite — 3 passed.
- Milestone 2: simulation suite — 11 passed. Two identical seeded 150-tick runs matched, and full event replay and snapshot replay matched their authoritative state hashes.
- Milestone 3: backend/API suite — 13 passed; strict frontend build and ESLint passed.
- Milestone 4: `make check` passed; `make dev` launched both servers. Docker Compose configuration validated, both Docker images built, and an isolated backend container returned `{"status":"ok"}` at `/health`.
- Milestone 5: Playwright/Chromium browser scenario passed (51.1 seconds including server startup). Exercised start, speed, pause, step, on-canvas character selection, roster selection, camera pan/zoom/center/fit, offline reconnect, 110 real ticks, MOVE/GATHER/EAT/REST records, replay hash equivalence, filters, reset and mobile layout. No uncaught page errors. Desktop/mobile screenshots: `artifacts/genesis-desktop.png`, `artifacts/genesis-mobile.png`.

A pacing test initially assumed two ticks within 150 ms. It was corrected to wait for observable advancement and verify pause stability, avoiding dependence on host throughput. The browser scenario initially exposed offline handling with an idle WebSocket; explicit offline/online handling and heartbeat resynchronization fixed it. The supplied Firefox automation had no GL driver; Chromium with software WebGL provided actual Pixi rendering verification.

Final `make check`: **17 backend tests passed**, Ruff and format checks passed, ESLint passed, strict TypeScript passed, and the production frontend build passed. The additional tests cover single-writer/database ownership, persisted restart recovery, death events, policy survival priorities, and same-seed reset equivalence.

Final commands and results are also available from running `make check`, `make e2e`, and `make replay`. npm audit after updating the development toolchain reported zero vulnerabilities. Docker image build/container health were tested; the full Compose pair was not started because the local development servers already occupied its ports.
