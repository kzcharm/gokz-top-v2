# Tech Stack - GOKZ.TOP v2

- Last Updated: 2026-05-18
- Source of truth: `backend/pyproject.toml`, `frontend/package.json`, `compose.yml`

## Architecture
- Monorepo with:
  - FastAPI backend in `backend/`
  - React + TypeScript frontend in `frontend/`
  - SourceMod plugin code tracked in the `sourcemod/` git submodule (`kzcharm/gokz-top-plugins-v2`)
- API surfaces:
  - `/v0` for GlobalAPI v2.0 compatibility behavior
  - `/v1` for project-native endpoints
  - `/v1/graphql` for player-focused GraphQL read queries
  - `/v1/live/streams` for the public verified-stream directory plus `/v1/live/preview-image` for approved external preview proxying of Bilibili preview assets
  - `/v1/admin/servers` for RBAC-protected server and server-group management
  - `/v1/admin/player-social-links` for superuser management of player social links and verification state
  - `/v1/maps/reviews` now supports website-authored review upserts plus authenticated comment-only deletion across a player's review rows for a map
- Data strategy:
  - PostgreSQL as primary persistent store
  - PostgreSQL-centric derived/cache artifacts (no Redis runtime dependency)
  - Ban rows are stored locally in PostgreSQL with an internal UUIDv7 primary key (`ban.uuid`) plus a nullable external GlobalAPI id (`ban.id`), allowing append/update-only mirrored GlobalAPI bans and superuser-created local bans to coexist in the same table
  - Scope-aware leaderboard read models are materialized in PostgreSQL from `record_pb` data and refreshed by a single midnight-UTC rank pipeline plus repair/backfill CLIs
  - The maps leaderboard is materialized in `cache.map_leaderboard`, keyed by `(map_id, scope)`, derived from raw valid stage-0 `record` rows, and joined with scoped map tiers plus map review summaries at read time
  - `map_course_tier`, keyed by `(course_id, mode)`, is now the v1 source of truth for course and map tier reads; `record_filter` is limited to availability metadata, and tier-bearing responses normalize to integers `0..8` with `0` meaning unavailable, impossible, or unknown
  - Main-map world-record reads are materialized in `cache.map_wrs`, derived from main-course `record_pb` rows, keyed by `(map_id, scope, type)`, and refreshed from record mutation flows
  - Player profile stats are cached in `cache.player_stats`, keyed by `(steamid64, type)`, and now include UTC daily activity, total playtime, and a grouped most-played-server breakdown aggregated from raw `record` rows and refreshed lazily on read after midnight-UTC expiry
  - Live CS server status uses PostgreSQL as the only shared cache/source of truth for browser reads
  - Player connection sessions are stored in `player_session` from SourceMod plugin events, keyed by plugin-generated UUIDv7 session IDs with PostgreSQL-generated duration seconds
  - Player sessions snapshot GeoIP country/region/city at ingest time for admin-only shared-IP traversal across exact IP, `/24`, and `/16 + city` buckets
  - Player self-service profile edits and rate-limited sync actions are tracked in `player_action_timestamp`, keyed by `(player_steamid64, action)`, with 30-day cooldown rows for `alias_change` and `custom_id_change`, a `country_manual_override` row that disables automatic country refreshes after a manual country change, and a one-minute `friends_sync` action used by the player friends sync flow
  - Automatic Steam/GlobalAPI/player-session country refreshes use the absence of a `player_action_timestamp(country_manual_override)` row as the gate for overwriting `player.country`, while manual user/admin country edits remain allowed
  - KZ-only player friendships are stored in `player_friend` as directed edges, with sync flows maintaining both directions for active friendships and deleting stale edges only after a successful Steam friends fetch
  - `player` now persists Steam friends visibility state through `friends_visibility` and `friends_visibility_checked_at`, allowing public profile reads to explain whether a Steam profile or friends list is private without storing generic sync-failure state
  - Player profile comments are stored in `player_comment`, keyed by UUIDv7 and linked to both author and target `player.steamid64`, with trimmed text validation, reverse-chronological profile reads, and owner-or-author deletion
  - Player social links are stored in `player_social_link` as platform-specific account identifiers, with URLs derived at API/UI edges and admin-controlled verification metadata
  - Player-owned Discord webhooks are stored in `player_webhook`, keyed by UUIDv7 and owned by `user.steamid64`, with per-webhook enablement and last-used timestamps
  - Live stream observations are stored in `live_stream_state`, keyed by `player_social_link.id`, and retain the last successful live metadata needed for `/live` offline history cards
  - Jumpstats are stored in `jumpstat`, keyed by UUIDv7, with scalar headline metrics plus per-strafe JSONB payloads, a nullable versioned `visualization_data` JSONB cache for replay-derived route samples, server-group-authenticated replay uploads accepted through `POST /v1/jumpstats`, and public reads served from `/v1/jumpstats`, `/v1/jumpstats/{id}/visualization`, and `/v1/players/{identifier}/jumpstats`
  - Uploaded/imported replay binaries are stored on disk under `REPLAY_STORAGE_DIR`, partitioned by replay type, with jump replays under `jumps/<jumpstat-id>.replay` and run replays under `runs/<normalized-map-name>/<record-uuid>.replay`
  - Historical run replays can be backfilled with the `app.import_run_replays` CLI, which accepts `.replay` files, directories, `.zip` archives, and `.7z` archives, requires v2 `NRM` style, matches exact player/mode/map/stage/time within a 24-hour `record.created_at` window, and skips ambiguous or already-imported replays
  - `/v1` record-shaped responses now expose `is_replay_available`, derived from run replay storage existence by `(map_name, record.uuid)` without changing `/v0` compatibility payloads
- Ranking read models:
  - `leaderboard_player` stores per-scope player aggregates for rating, tier-split rating, total points, WR counts, high-point record counts, and unique validated main-map finishes
  - `leaderboard_player` rows only exist for players with at least 10 unique validated main-map finishes in scope and no active mirrored ban; rebuilds delete rows that fall below the threshold or become actively banned
  - `GET /v1/leaderboards/players` reads from `leaderboard_player` with order-specific composite indexes for the supported sort modes and a cached per-scope count read model for shared no-geo totals
  - Active mirrored bans are enforced as query-time exclusions for selected leaderboard and record reads via `EXISTS`/`NOT EXISTS` predicates instead of direct joins
- Live server status subsystem:
  - Public reads come from cached `/v1/servers` and `/v1/servers/{id}` responses only; browsers never trigger upstream A2S or Steam server-list queries
  - SourceMod server heartbeats are sent by `gokz-top-servers`, which reuses `gokz-top-core` auth config and resolves the target server by cached public IPv4 plus `hostport`
  - Plugin heartbeats ingest through `PUT /v1/servers/status` with a server-group API key and resolve servers by `(ip, port)`
  - Plugin heartbeat player payloads are typed and richer than A2S player rows, including GOKZ timer status, mode, teleports, timer time, pause state, stage, and per-connection duration
  - Player session events ingest through `/v1/player-sessions/connect`, `/heartbeat`, and `/disconnect` with `X-Server-Group-Key`; server group identity is derived from the API key rather than request JSON
  - Superuser session investigations use `/v1/admin/player-sessions/ip-links` to traverse shared-IP session buckets with bounded depth and busy-bucket skipping
  - Discovery uses Steam `IGameServersService/GetServerList` across regions `0..7`, with a one-hour background interval and a superuser-triggered manual run endpoint
  - A separate collector process handles Steam server-list discovery, A2S refresh, offline marking, and raw heartbeat partition maintenance
  - WebSocket updates are delivered from `/v1/ws/servers` after cache updates, using PostgreSQL `LISTEN/NOTIFY` to fan out change events from the backend
- Scheduled background maintenance:
  - Continuous GlobalAPI sync remains responsible for ingesting mirrored upstream records and other mirrored entities
  - A single in-app midnight-UTC rank pipeline selects the previous UTC day's changed `record_pb` rows, rebuilds touched PB point buckets, rebuilds touched leaderboard rows, rebuilds touched maps leaderboard rows selected from `Record.updated_at`, refreshes touched player Steam profiles, and then attempts KZ-only friends sync for those same players
  - An advisory-locked in-app player-session timeout runner closes open sessions after the configured heartbeat timeout by setting `disconnect_at` to the last heartbeat timestamp
  - An advisory-locked in-app live-stream runner polls verified Bilibili and Twitch social links on a fixed interval, caches Twitch app tokens in-process, and updates `live_stream_state` without clearing live rows on transport failures
  - The midnight rank pipeline preserves `record_pb.updated_on` during point recalculation so same-day retries keep the same selection window

## Backend Runtime and Libraries
- Python `>=3.14,<4.0`
- FastAPI (`fastapi[standard]`)
- strawberry-graphql
- Pydantic v2
- SQLModel
- Alembic
- psycopg3 (`psycopg[binary]`)
- pydantic-settings
- httpx
- python-multipart
- tenacity
- pyjwt
- py7zr
- pwdlib (`argon2`, `bcrypt`)
- sentry-sdk (FastAPI integration)

## Backend Quality Tooling
- uv for environment and dependency management
- Ruff for linting
- mypy (strict mode)
- pytest + pytest-asyncio
- coverage (CI threshold target >= 90%)

## Frontend Runtime and Libraries
- React 19
- TypeScript 5.9
- Vite 7 + `@vitejs/plugin-react-swc`
- Tailwind CSS 4 + `@tailwindcss/vite`
- Radix UI primitives
- TanStack:
  - React Router
  - React Query
  - React Table
- Forms and validation:
  - react-hook-form
  - @hookform/resolvers
  - zod
- HTTP and utilities:
  - axios
  - graphql-request
  - clsx
  - class-variance-authority
  - tailwind-merge
- UI helpers:
  - next-themes
  - i18next + react-i18next with app-level locale persistence in `localStorage` (`gokz-language`)
  - sonner
  - lucide-react
  - react-icons
- Generated API client:
  - @hey-api/openapi-ts
  - frontend review authoring flows read both latest-review and website-review variants from the generated `/v1/maps/reviews` contract

## Frontend Tooling and Tests
- Bun workspace scripts at repository root
- Node.js 24 for local npm-compatible frontend tooling
- Biome for linting/formatting
- Playwright for end-to-end tests

## Infrastructure and Operations
- Docker + Docker Compose
- PostgreSQL 18 container (`postgres:18`)
- Traefik for reverse proxy/routing
- Adminer for DB admin
- Frontend served by Nginx in production container

## External Integrations
- Steam OpenID and Steam Web API integration paths exist in backend flows.
- GlobalAPI endpoints are consumed for synchronization/compatibility behavior.
- GlobalAPI record-filter sync now mirrors availability rows only, ensures exact 128-tick `map_course` rows for locally known maps, and does not derive non-VNL course tiers from upstream filter data after the one-time backfill migration.
- Twitch Helix API is consumed for verified Twitch live-stream status using app credentials.
- GlobalAPI ban sync upserts by nullable external `ban.id`, uses large backfill pages for catch-up, then incremental `created_since` overlap polling with a steady-state page size of `10`, and ignores local manual bans because they do not carry an external id.

## Implementation Constraints
- Do not hand-edit generated frontend files:
  - `frontend/src/client/*`
  - `frontend/src/routeTree.gen.ts`
- Keep compatibility behavior under `/v0` stable; project-native changes should go to `/v1`.
- Treat 64-bit identifiers such as `steamid64` as strings at all API and frontend boundaries. Do not send them as JavaScript numbers, because precision loss can silently break queries and mutations. Convert to integers only inside backend internals when numeric DB comparisons are required.
- `/v0/bans` remains a mirrored-GlobalAPI compatibility surface and excludes local manual bans, while `/v1/bans` returns both mirrored and local bans, exposes both `uuid` and nullable `id`, supports superuser `POST /v1/bans` manual creation, and uses UUIDs for `/v1/bans/{uuid}` detail reads.
- Use UUIDv7 for new UUID fields/defaults and update touched UUID defaults to UUIDv7 unless compatibility requires otherwise.
- Frontend destructive actions should use the destructive red visual treatment consistently, including icon-only delete buttons in tables and settings surfaces.
- Short frontend field titles and settings/tab labels should use title case in English copy, capitalizing the first letter of each word (for example `Steam Name`, `Social Links`, `Country / Region`).

## Local Admin Testing
- For manual local browser testing of admin-only pages, do not enable `/v1/private/auth/session` by default.
- The preferred flow is to mint a normal local JWT for `settings.SUPER_USER_STEAMID64` using `backend/app/core/security.py`, then open the frontend callback route with that token:
  - generate a token from the backend environment with `create_access_token(settings.SUPER_USER_STEAMID64, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))`
  - visit `http://localhost:5173/auth/callback#access_token=<token>` to let the frontend store the token through its normal auth callback path
  - then open the target admin page, such as `http://localhost:5173/admin/player-social-links`
- This keeps manual QA closer to the real production auth path and avoids exposing the dev-only private auth helper during ordinary local development.
- Only enable `ENABLE_TEST_AUTH_HELPERS=true` and the `/v1/private/auth/session` helper for explicit automated test runs or disposable local test environments.
