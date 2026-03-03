# CSGO/CS2 Server Live Status Plan (Hybrid Push + Pull)

- Date: 2026-03-03
- Scope: Design a live server status system for map/player/activity data with richer data than A2S-only polling.

## Goals

1. Keep GlobalAPI `v2` compatibility while adding richer `v3` live status.
2. Support near real-time server status for frontend (map, players, tickrate, tags, etc.).
3. Handle server hibernation correctly so "sleeping empty server" is not misclassified as offline.
4. Keep source of truth for servers independent from stale GlobalAPI upstream server list.

## Key Decisions

1. Use a hybrid model:
   - Push: game server plugin sends heartbeat/status events to backend.
   - Pull: backend performs periodic A2S queries for verification and fallback.
2. New server metadata source of truth table/model:
   - Table: `core.server_registry`
   - Model: `ServerRegistry`
3. Keep compatibility-facing server table separate:
   - Table: `core.server`
   - Model: `Server` (for GlobalAPI-compatible behaviors)
4. Use HTTP POST heartbeats first (not server-initiated WebSocket):
   - Simpler in SourceMod/plugin environments
   - Easier retries and auth
   - Better reliability behind NAT/firewalls

## Recommended Stack

1. Backend API: FastAPI (existing project stack)
2. Query worker: Python async worker using `python-a2s`
3. Database: PostgreSQL
4. Realtime delivery to frontend: backend WebSocket + REST fallback
5. Scheduling: app worker loop and/or `pg_cron` for recurring probes

## Data Model Plan

## 1) Server Metadata (authoritative list)
- Table: `core.server_registry`
- Purpose: internal source of truth for managed servers
- Suggested columns:
  - `id` (PK)
  - `name`
  - `host`
  - `game_port`
  - `query_port` (nullable, can differ from game port)
  - `owner_steamid64`
  - `source` (`globalapi` | `manual` | `plugin`)
  - `globalapi_server_id` (nullable link/reference)
  - `is_enabled`
  - `is_public`
  - `created_at`, `updated_at`

## 2) Current Status Cache (latest row per server)
- Table: `cache.server_status_current`
- Purpose: fast read path for `/api/v3/servers/status`
- Suggested columns:
  - `server_id` (PK/FK)
  - `presence_state` (`online_active`, `online_empty`, `hibernating`, `offline`)
  - `presence_reason`
  - `map`
  - `mode`
  - `tickrate`
  - `player_count`
  - `max_players`
  - `players_json` (optional compact roster)
  - `last_push_at`
  - `last_a2s_at`
  - `last_non_empty_at`
  - `consecutive_a2s_failures`
  - `updated_at`

## 3) Raw Push Events
- Table: `core.server_status_ingest`
- Purpose: append-only raw payloads from game server plugin
- Suggested columns:
  - `id`
  - `server_id`
  - `event_type` (`heartbeat`, `empty_server`, `wakeup`, `map_change`, etc.)
  - `payload_json`
  - `received_at`
  - `signature_valid`

## 4) Historical Snapshots
- Table: `core.server_status_history`
- Purpose: analytics, debugging, trend charts
- Notes: partition by day/week if needed

## 5) Probe Queue / Coordination
- Table: `core.server_probe_job`
- Purpose: worker-safe scheduling with `FOR UPDATE SKIP LOCKED`
- Fields: `server_id`, `next_run_at`, `priority`, `attempts`, `last_error`

## API Contract Plan (V3)

1. `POST /api/v3/servers/{server_id}/heartbeat`
   - Auth: `X-ApiKey` + request signature headers
   - Cadence: every 5-10s while active
2. `GET /api/v3/servers/status`
   - Reads from `cache.server_status_current`
3. `GET /api/v3/servers/{server_id}/status`
   - Single-server current status
4. `GET /api/v3/servers/{server_id}/status/history`
   - Time-bounded historical snapshots
5. `WS /api/v3/servers/status/stream`
   - Backend pushes state changes to web clients

## Security Plan for Push Endpoint

1. Sign request with HMAC:
   - Canonical string: `method + path + timestamp + nonce + body_hash`
2. Headers:
   - `X-Timestamp`, `X-Nonce`, `X-Signature`
3. Reject if:
   - Timestamp skew > 30s
   - Nonce replay detected
   - Signature mismatch
4. Add per-server rate limits.

## Hibernation-Aware Presence State Machine

## States
1. `online_active`: recent push, `player_count > 0`
2. `online_empty`: recent push, `player_count = 0`
3. `hibernating`: push stale, last state empty, A2S still reachable
4. `offline`: no recent push and A2S failed past threshold

## Transitions
1. Push heartbeat with players > 0 -> `online_active`
2. Push heartbeat with players = 0 -> `online_empty` and mark `can_hibernate=true`
3. No push for 20-30s while last state is `online_empty` -> `hibernating`
4. In `hibernating`, poll A2S every 60-120s:
   - A2S success -> stay `hibernating`
   - A2S fail N times (example: 3) or stale > 10 min -> `offline`
5. Any new push -> leave `hibernating` immediately

## Plugin Event Recommendations

1. Final event when last player leaves:
   - `event_type = "empty_server"`
   - `player_count = 0`
   - `will_hibernate = true`
2. Wake event on first join/round live:
   - `event_type = "wakeup"`
3. Optional map lifecycle events:
   - `map_change_start`, `map_change_end`

## Polling Strategy

1. Active servers (`online_active`): A2S every 20-30s (or longer if push is trusted).
2. Empty/hibernating servers: A2S every 60-120s.
3. Offline servers: exponential backoff probing.
4. Always keep pull path as safety net for spoofed/missed pushes.

## Frontend Behavior

1. Display statuses distinctly:
   - `Online`
   - `Online (Empty)`
   - `Sleeping` (hibernating)
   - `Offline`
2. Never label hibernation as outage.
3. Update via WebSocket, fallback to periodic REST fetch.

## Implementation Phases

1. Create schema/tables/models (`server_registry`, status tables).
2. Implement secure heartbeat endpoint and ingestion pipeline.
3. Implement status reducer/upsert into `cache.server_status_current`.
4. Add A2S worker + probe queue.
5. Implement hibernation state transitions.
6. Add v3 REST + WebSocket endpoints.
7. Add frontend state labels and filters.
8. Add tests (state machine, auth signature, fallback behavior).

## Acceptance Criteria

1. Server can be tracked live with map/player data when push is active.
2. Empty hibernating servers show as `Sleeping`, not `Offline`.
3. When push stops unexpectedly, A2S fallback keeps status accurate.
4. System tolerates missed heartbeats and recovers on next push.
5. `v3` status endpoint p95 latency meets target from cache table.
