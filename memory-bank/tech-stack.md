# Tech Stack - GOKZ.TOP v2

- Last Updated: 2026-05-05
- Source of truth: `backend/pyproject.toml`, `frontend/package.json`, `compose.yml`

## Architecture
- Monorepo with:
  - FastAPI backend in `backend/`
  - React + TypeScript frontend in `frontend/`
- API surfaces:
  - `/v0` for GlobalAPI v2.0 compatibility behavior
  - `/v1` for project-native endpoints
  - `/v1/graphql` for player-focused GraphQL read queries
  - `/v1/admin/servers` for RBAC-protected server and server-group management
  - `/v1/admin/player-social-links` for superuser management of player social links and verification state
  - `/v1/maps/reviews` now supports website-authored review upserts plus authenticated comment-only deletion across a player's review rows for a map
- Data strategy:
  - PostgreSQL as primary persistent store
  - PostgreSQL-centric derived/cache artifacts (no Redis runtime dependency)
  - Mirrored GlobalAPI ban rows are stored locally in PostgreSQL with a PostgreSQL enum-backed `ban_type` and append/update-only sync semantics
  - Scope-aware leaderboard read models are materialized in PostgreSQL from `record_pb` data and refreshed by a single midnight-UTC rank pipeline plus repair/backfill CLIs
  - The maps leaderboard is materialized in `cache.map_leaderboard`, keyed by `(map_id, scope)`, derived from raw valid stage-0 `record` rows, and joined with scoped map tiers plus map review summaries at read time
  - Main-map world-record reads are materialized in `cache.map_wrs`, derived from main-course `record_pb` rows, keyed by `(map_id, scope, type)`, and refreshed from record mutation flows
  - Player profile stats are cached in `cache.player_stats`, keyed by `(steamid64, type)`, and now include UTC daily activity plus total playtime aggregated from raw `record` rows and refreshed lazily on read after midnight-UTC expiry
  - Live CS server status uses PostgreSQL as the only shared cache/source of truth for browser reads
  - Player connection sessions are stored in `player_session` from SourceMod plugin events, keyed by plugin-generated UUIDv7 session IDs with PostgreSQL-generated duration seconds
  - Player sessions snapshot GeoIP country/region/city at ingest time for admin-only shared-IP traversal across exact IP, `/24`, and `/16 + city` buckets
  - Player self-service profile edits are tracked in `player_profile_field_change`, keyed by `(player_steamid64, field)`, with 30-day cooldown rows for `alias` and `custom_id` plus a `country` row that disables automatic country refreshes after a manual country change
  - Automatic Steam/GlobalAPI/player-session country refreshes use the absence of a `player_profile_field_change(country)` row as the gate for overwriting `player.country`, while manual user/admin country edits remain allowed
  - Player social links are stored in `player_social_link` as platform-specific account identifiers, with URLs derived at API/UI edges and admin-controlled verification metadata
- Ranking read models:
  - `leaderboard_player` stores per-scope player aggregates for rating, tier-split rating, total points, WR counts, high-point record counts, and unique validated main-map finishes
  - `leaderboard_player` rows only exist for players with at least 10 unique validated main-map finishes in scope and no active mirrored ban; rebuilds delete rows that fall below the threshold or become actively banned
  - `GET /v1/leaderboards/players` reads from `leaderboard_player` with order-specific composite indexes for the supported sort modes and a cached per-scope count read model for shared no-geo totals
  - Active mirrored bans are enforced as query-time exclusions for selected leaderboard and record reads via `EXISTS`/`NOT EXISTS` predicates instead of direct joins
- Live server status subsystem:
  - Public reads come from cached `/v1/servers` and `/v1/servers/{id}` responses only; browsers never trigger upstream A2S or Steam server-list queries
  - Plugin heartbeats ingest through `PUT /v1/servers/status` with a server-group API key and resolve servers by `(ip, port)`
  - Player session events ingest through `/v1/player-sessions/connect`, `/heartbeat`, and `/disconnect` with `X-Server-Group-Key`; server group identity is derived from the API key rather than request JSON
  - Superuser session investigations use `/v1/admin/player-sessions/ip-links` to traverse shared-IP session buckets with bounded depth and busy-bucket skipping
  - Discovery uses Steam `IGameServersService/GetServerList` across regions `0..7`, with a one-hour background interval and a superuser-triggered manual run endpoint
  - A separate collector process handles Steam server-list discovery, A2S refresh, offline marking, and raw heartbeat partition maintenance
  - WebSocket updates are delivered from `/v1/ws/servers` after cache updates, using PostgreSQL `LISTEN/NOTIFY` to fan out change events from the backend
- Scheduled background maintenance:
  - Continuous GlobalAPI sync remains responsible for ingesting mirrored upstream records and other mirrored entities
  - A single in-app midnight-UTC rank pipeline selects the previous UTC day's changed `record_pb` rows, rebuilds touched PB point buckets, rebuilds touched leaderboard rows, rebuilds touched maps leaderboard rows selected from `Record.updated_at`, and refreshes touched player Steam profiles
  - An advisory-locked in-app player-session timeout runner closes open sessions after the configured heartbeat timeout by setting `disconnect_at` to the last heartbeat timestamp
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
- GlobalAPI ban sync uses large backfill pages for catch-up, then incremental `updated_since` polling with a steady-state page size of `10`.

## Implementation Constraints
- Do not hand-edit generated frontend files:
  - `frontend/src/client/*`
  - `frontend/src/routeTree.gen.ts`
- Keep compatibility behavior under `/v0` stable; project-native changes should go to `/v1`.
- Use UUIDv7 for new UUID fields/defaults and update touched UUID defaults to UUIDv7 unless compatibility requires otherwise.
