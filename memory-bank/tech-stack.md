# Tech Stack - GOKZ.TOP v2

- Last Updated: 2026-06-08
- Source of truth: `backend/pyproject.toml`, `frontend/package.json`, `compose.yml`

## Architecture
- Monorepo with:
  - FastAPI backend in `backend/`
  - React + TypeScript frontend in `frontend/`
  - SourceMod plugin code tracked in the `sourcemod/` git submodule (`kzcharm/gokz-top-plugins`)
  - GOKZ replay viewer tracked in the `replay-viewer/` git submodule (`kzcharm/replay-viewer`) and deployed as a separate Traefik-routed frontend service
- API surfaces:
  - `/v0` for GlobalAPI v2.0 compatibility behavior
  - `/v1` for project-native endpoints
  - `/v1/graphql` for player-focused GraphQL read queries
  - `/v1/live/streams` for the public verified-stream directory plus `/v1/live/preview-image` for approved external preview proxying of Bilibili preview assets
  - `/v1/me/notifications` for authenticated player notification inbox reads, unread counts, and read-state mutations
  - `/v1/admin/servers` for RBAC-protected server and server-group management
  - `/v1/admin/player-social-links` for superuser management of player social links and verification state
  - `/v1/maps/reviews` now supports website-authored review upserts plus authenticated comment-only deletion across a player's review rows for a map
- Data strategy:
  - PostgreSQL as primary persistent store
  - PostgreSQL-centric derived/cache artifacts (no Redis runtime dependency)
  - Ban rows are stored locally in PostgreSQL with an internal UUIDv7 primary key (`ban.uuid`) plus a nullable external GlobalAPI id (`ban.id`), allowing append/update-only mirrored GlobalAPI bans and superuser-created local bans to coexist in the same table
  - Scope-aware leaderboard read models are materialized in PostgreSQL from `record_pb` data and refreshed by a single midnight-UTC rank pipeline plus repair/backfill CLIs
  - `record_pb.raw_rating_contribution` stores the per-PB-row raw rating contribution assigned during player leaderboard rebuilds, so record list APIs can show how each contributing PB feeds the player's raw rating
  - The maps leaderboard is materialized in `cache.map_leaderboard`, keyed by `(map_id, scope)`, derived from raw valid stage-0 `record` rows, and joined with scoped map tiers plus map review summaries at read time
  - `map_course_tier`, keyed by `(course_id, mode)`, is now the v1 source of truth for course and map tier reads; `record_filter` is limited to availability metadata, and tier-bearing responses normalize to integers `0..8` with `0` meaning unavailable, impossible, or unknown
  - Main-map world-record reads are materialized in `cache.map_wrs`, derived from main-course `record_pb` rows, keyed by `(map_id, scope, type)`, and refreshed from record mutation flows
  - Player profile stats are cached in `cache.player_stats`, keyed by `(steamid64, type)`, and now include UTC daily activity, total playtime, grouped most-played-server breakdowns, and top-10 most-played-map breakdowns by record count and record time aggregated from raw `record` rows and refreshed lazily on read after midnight-UTC expiry; most-played-server rebuilds auto-update `player.favorite_server_id` or `player.favorite_server_group_id` unless a manual favorite override action exists
  - Live CS server status uses PostgreSQL as the only shared cache/source of truth for browser reads
  - Player connection sessions are stored in `player_session` from SourceMod plugin events, keyed by plugin-generated UUIDv7 session IDs with PostgreSQL-generated duration seconds
  - Player sessions snapshot GeoIP country/region/city at ingest time for admin-only shared-IP traversal across exact IP, `/24`, and `/16 + city` buckets
  - Player self-service profile edits and rate-limited sync actions are tracked in `player_action_timestamp`, keyed by `(player_steamid64, action)`, with 30-day cooldown rows for `alias_change` and `custom_id_change`, a `country_manual_override` row that disables automatic country refreshes after a manual country change, a `favorite_server_manual_override` row that disables favorite-server auto-updates after any manual favorite choice including `None`, and a one-minute `friends_sync` action used by the player friends sync flow
  - Automatic Steam/GlobalAPI/player-session country refreshes use the absence of a `player_action_timestamp(country_manual_override)` row as the gate for overwriting `player.country`, while manual user/admin country edits remain allowed
  - KZ-only player friendships are stored in `player_friend` as directed edges, with sync flows maintaining both directions for active friendships and deleting stale edges only after a successful Steam friends fetch
  - `player` now persists Steam friends visibility state through `friends_visibility` and `friends_visibility_checked_at`, allowing public profile reads to explain whether a Steam profile or friends list is private without storing generic sync-failure state
  - `player.favorite_server_id` and `player.favorite_server_group_id` persist the resolved favorite server target with a check constraint allowing at most one target; grouped favorites display and link through the server group summary shape
  - Player profile comments are stored in `player_comment`, keyed by UUIDv7 and linked to both author and target `player.steamid64`, with trimmed text validation, reverse-chronological profile reads, and owner-or-author deletion
  - Player notifications are stored in `player_notification`, keyed by UUIDv7 with an idempotent `source_key`, recipient/actor Steam IDs, read timestamps, target URLs, and typed payload fields for profile likes, profile comments, follows, and future-only WR-beaten events
  - Player social links are stored in `player_social_link` as platform-specific account identifiers, with URLs derived at API/UI edges; Twitch and YouTube support OAuth self-verification, Bilibili supports profile-code self-verification, and admins can still manage verification metadata
  - Verified Bilibili, YouTube, and Twitch follower counts for community leaderboard display are cached in `cache.player_video_platform_followers`, keyed by `player_social_link.id`, and refreshed lazily with a TTL so public reads do not depend on live platform API success
  - Player-owned Discord webhooks are stored in `player_webhook`, keyed by UUIDv7 and owned by `user.steamid64`, with per-webhook enablement and last-used timestamps
  - Live stream observations are stored in `live_stream_state`, keyed by `player_social_link.id`, and retain the last successful live metadata needed for `/live` offline history cards
  - Cloudflare R2 is available as a reusable S3-compatible object storage integration when `R2_*` settings are configured; staging and production deployments use separate bucket/public-url secrets, live stream polling stores the latest Bilibili and Twitch keyframe objects there while keeping their public URLs in `live_stream_state.last_keyframe_image_url`, and the production-only map file distributor uploads BSP, optional BZ2, full `GlobalMaps.7z`, and per-date release ZIP objects there
  - Map file distribution stores long-lived raw BSPs plus the full `GlobalMaps.7z` archive under `MAP_FILE_STORAGE_DIR`, with optional manual seeding from an operator-provided starter package and SteamCMD-based Workshop refreshes for new or updated maps
  - Jumpstats are stored in `jumpstat`, keyed by UUIDv7, with scalar headline metrics plus per-strafe JSONB payloads, a nullable versioned `visualization_data` JSONB cache for replay-derived route samples, server-group-authenticated replay uploads accepted through multipart `POST /v1/jumpstats` and raw `POST /v1/jumpstats/replay`, eligibility pre-checks served by `GET /v1/jumpstats/replay-eligibility`, and public reads served from `/v1/jumpstats`, `/v1/jumpstats/{id}/visualization`, and `/v1/players/{identifier}/jumpstats`
  - Uploaded/imported replay binaries are stored on disk under `REPLAY_STORAGE_DIR`, partitioned by replay type, with jump replays under `jumps/<jumpstat-id>.replay` and run replays under `runs/<normalized-map-name>/<record-uuid>.replay`
  - Jump replay retention is per player and mode: the app keeps the best 10 `LJ` replay files and the best replay file for each other supported jump type, while an advisory-locked in-app cleanup runner deletes old non-kept jump replay files after the configured grace period without deleting `jumpstat` rows
  - Historical run replays can be backfilled with the `app.import_run_replays` CLI, which accepts `.replay` files, directories, `.zip` archives, and `.7z` archives, requires v2 `NRM` style, matches exact player/mode/map/stage/time within a 24-hour `record.created_at` window, and skips ambiguous or already-imported replays
  - `/v1` record-shaped responses now expose `is_replay_available`, derived from run replay storage existence by `(map_name, record.uuid)` without changing `/v0` compatibility payloads
- Ranking read models:
  - `leaderboard_player` stores per-scope player aggregates for rating, tier-split rating, total points, WR counts, high-point record counts, and unique validated main-map finishes
  - Player leaderboard rebuilds also refresh `record_pb.raw_rating_contribution`, assigning each eligible course's decay-weighted raw rating term to the deterministic best PB row and zeroing non-contributing rows
  - `leaderboard_player` rows only exist for players with at least 10 unique validated main-map finishes in scope and no active mirrored ban; rebuilds delete rows that fall below the threshold or become actively banned
  - `GET /v1/leaderboards/players` reads from `leaderboard_player` with order-specific composite indexes for the supported sort modes and a cached per-scope count read model for shared no-geo totals
  - `GET /v1/leaderboards/community` returns profile-view/like rankings plus the highest cached verified platform follower count among Bilibili, YouTube, and Twitch for each returned player, and supports sorting by `platform_followers`
  - Active mirrored bans are enforced as query-time exclusions for selected leaderboard and record reads via `EXISTS`/`NOT EXISTS` predicates instead of direct joins
- Live server status subsystem:
  - Public reads come from cached `/v1/servers` and `/v1/servers/{id}` responses only; browsers never trigger upstream A2S or Steam server-list queries
  - SourceMod server heartbeats are sent by `gokz-top-servers`, which reuses `gokz-top-core` auth config and resolves the target server by cached public IPv4 plus `hostport`
  - SourceMod in-game profile/rating reads are served by `gokz-top-profile`, which preserves the legacy `gokz-profile` library/native surface while reading cached `/v1/leaderboards/players/{identifier}` data through `gokz-top-core`
  - Plugin heartbeats ingest through `PUT /v1/servers/status` with a server-group API key and resolve servers by `(ip, port)`
  - Plugin heartbeat player payloads are typed and richer than A2S player rows, including GOKZ timer status, mode, teleports, timer time, pause state, stage, and per-connection duration
  - Player session events ingest through `/v1/player-sessions/connect`, `/heartbeat`, and `/disconnect` with `X-Server-Group-Key`; server group identity is derived from the API key rather than request JSON
  - Superuser session investigations use `/v1/admin/player-sessions/ip-links` to traverse shared-IP session buckets with bounded depth and busy-bucket skipping
  - Discovery uses Steam `IGameServersService/GetServerList` across regions `0..7`, with a one-hour background interval and a superuser-triggered manual run endpoint
  - A separate collector process handles Steam server-list discovery, A2S refresh, offline marking, and raw heartbeat partition maintenance
  - WebSocket updates are delivered from `/v1/ws/servers` after cache updates, using PostgreSQL `LISTEN/NOTIFY` to fan out change events from the backend
- Scheduled background maintenance:
  - Continuous GlobalAPI sync remains responsible for ingesting mirrored upstream records and other mirrored entities
  - Forward GlobalAPI record sync emits WR-beaten notifications for future KZT/SKZ/VNL NUB and PRO world-record owner changes while repair/backfill paths avoid historical notification floods
  - A single in-app midnight-UTC rank pipeline selects the previous UTC day's changed `record_pb` rows, rebuilds touched PB point buckets, rebuilds touched leaderboard rows, rebuilds touched maps leaderboard rows selected from `Record.updated_at`, refreshes touched player Steam profiles, and then attempts KZ-only friends sync for those same players
  - An advisory-locked in-app player-session timeout runner closes open sessions after the configured heartbeat timeout by setting `disconnect_at` to the last heartbeat timestamp
  - An advisory-locked in-app live-stream runner polls verified Bilibili and Twitch social links on a fixed interval, caches Twitch app tokens in-process, and updates `live_stream_state` without clearing live rows on transport failures
  - An advisory-locked in-app jump replay cleanup runner periodically deletes replay files older than the retention grace period when their jumpstat row no longer ranks inside the per-player/mode keep set
  - A dedicated production `map-distributor` worker runs map BSP distribution after daily map sync, uses SteamCMD anonymous Workshop downloads for updated maps, updates a persisted full 7z package incrementally when possible, and exposes BSP URLs through map API `download_url`
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
- Replay viewer served by its own Nginx production container at `replays.gokz.top`, with exported map resources mounted read-only from the host instead of copied into git or baked into the image

## External Integrations
- Steam OpenID and Steam Web API integration paths exist in backend flows.
- GlobalAPI endpoints are consumed for synchronization/compatibility behavior.
- GlobalAPI record-filter sync now mirrors availability rows only, ensures exact 128-tick `map_course` rows for locally known maps, and does not derive non-VNL course tiers from upstream filter data after the one-time backfill migration.
- Twitch Helix API is consumed for verified Twitch live-stream status and cached Twitch follower counts using app credentials.
- Cloudflare R2 can be consumed through its S3-compatible API for app-managed public object storage.
- SteamCMD is used by the production map file distributor to download Workshop map BSPs for app id `730`.
- YouTube Data API can be consumed with `YOUTUBE_API_KEY` to refresh cached YouTube subscriber counts for verified social links, and Google OAuth credentials (`YOUTUBE_CLIENT_ID`/`YOUTUBE_CLIENT_SECRET`) power self-serve YouTube social-link verification.
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
- Avoid filler UI copy that restates obvious page behavior or adds generic descriptive text without helping the user complete a task; only add explanatory copy when it conveys concrete, decision-relevant information.

## Local Admin Testing
- For manual local browser testing of admin-only pages, do not enable `/v1/private/auth/session` by default.
- The preferred flow is to mint a normal local JWT for `settings.SUPER_USER_STEAMID64` using `backend/app/core/security.py`, then open the frontend callback route with that token:
  - generate a token from the backend environment with `create_access_token(settings.SUPER_USER_STEAMID64, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))`
  - visit `http://localhost:5173/auth/callback#access_token=<token>` to let the frontend store the token through its normal auth callback path
  - then open the target admin page, such as `http://localhost:5173/admin/player-social-links`
- This keeps manual QA closer to the real production auth path and avoids exposing the dev-only private auth helper during ordinary local development.
- Only enable `ENABLE_TEST_AUTH_HELPERS=true` and the `/v1/private/auth/session` helper for explicit automated test runs or disposable local test environments.
