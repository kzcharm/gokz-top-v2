# Tech Stack - GOKZ.TOP v2

- Last Updated: 2026-10-27
- Source of truth: `backend/pyproject.toml`, `frontend/package.json`, `compose.yml`

## Architecture
- Map preview WebPs are mirrored daily from KZGlobalTeam/map-images into a stack-specific persistent `map-image-data` volume; the advisory-locked backend runner and `kztop sync map-images` share incremental blob-hash validation. Public `/v1/maps/images/{map_name}.webp` reads use seven-day browser/Cloudflare cache headers and conditional validators. GraphQL selects local images first; the frontend loads sources sequentially and retains direct Steam Workshop fallback. Cache Rules inspection requires permissions beyond the current DNS token.
- Public `/cards/player/:identifier` is a static portrait capture surface with explicit loading/ready/error states. The official QQ bot captures it with its existing Chromium at 480 CSS pixels and 2× resolution; two concurrent workers, request deduplication, and a 15-minute cache keep rendering bounded. `GOKZ_TOP_WEBSITE_URL` selects the website environment. Card identity reads use the existing player endpoint with `refresh_steam_profile=false` to include favorite-server details without scheduling Steam synchronization; ordinary reads default to refreshing.
- Monorepo with:
  - FastAPI backend in `backend/`
  - React + TypeScript frontend in `frontend/`
  - SourceMod plugin code tracked in the `sourcemod/` git submodule (`kzcharm/gokz-top-plugins`)
  - Official QQ and Discord NoneBot application tracked in the `qqbot/` git submodule (`kzcharm/qqbot-saki-chan`), with its own deployment on E
  - GOKZ replay viewer tracked in the `replay-viewer/` git submodule (`kzcharm/replay-viewer`) and deployed as a separate Traefik-routed frontend service
- API surfaces:
  - `/v0` for GlobalAPI v2.0 compatibility behavior
  - `/v1` for project-native endpoints
  - `/v1/graphql` for selectively hydrated player data and batched map-preview URL reads
  - Public player display roles include server-group and GlobalAPI server ownership only for players with a website User account, without mutating stored account roles; role rings prioritize superuser, admin, map admin, server owner, then normal website user. Non-users have no role ring, including server owners.
  - Player GraphQL hydration includes `isOnline`, matched in one batch against enabled public server rosters updated within 30 seconds. Shared `PlayerActivityBadge` indicators on `PlayerDisplay` and main profile avatars refresh every 30 seconds and show green in-server, blue last-played-within-seven-days, or solid gray inactive-for-at-least-one-year badges (no badge for seven-days-to-one-year gaps or unknown activity); static player cards omit presence badges.
  - `/v1/ws/players` for live completion events when an on-demand Steam player-profile refresh changes visible identity data
  - `/v1/ws/records/recent` for scope-aware live record events, with an optional `steamid64` subscription filter used by a player's own runs page
  - `/v1/records/wrs/recent` and `/v1/ws/records/wrs/recent` for the paginated, filterable historical main-course WR event feed and live page-one snapshots
  - Profile run WR columns join `/v1/records/pb` results with the matching scoped `/v1/maps/wrs` response in the frontend; the WR response includes the winning run's teleport count for PRO/TP color treatment, and the PB endpoint does not perform per-record WR enrichment
  - `/v1/records/pb` optionally returns live `rank` values with `include_ranks=true`. A batched indexed count of eligible earlier `(time, record_uuid)` entries ranks only the returned PBs within their scope/type/course/geography; active bans are excluded. The profile Runs table's cookie-persisted Show ranks option defaults off and gates rank requests. The profile fetches unranked PBs once, then uses `/v1/records/pb/ranks` for only the visible page (1–50 UUIDs, separate scoped cache). Enabling ranks forces pagination capped at 50; rank sorting is page-local. PB responses with `include_ranks=true` are also capped at 50. PB rank enrichment deliberately omits leaderboard total counts; `/v1/records/rank` retains those separately.
  - `/v1/records/pb/first-completions` returns compact earliest valid finish datetimes by map/stage for one player and scope/type. It uses one grouped historical query with existing player indexes. Profile Runs fetches it separately only when Show first completion time is enabled, shares PB invalidation, and sorts the full loaded collection before pagination. Activation resets on leaving Runs, changing player, or reload; local 27.6M-record benchmarks found initial reads around four seconds despite warm p95 below 200 ms. No schema change or server-side cache is required.
  - `/v1/live/streams` for the public verified-stream directory plus `/v1/live/preview-image` for approved external preview proxying of Bilibili preview assets
  - `/v1/maps/lj-rooms` for unauthenticated, map-name-addressed LJ-room coordinates consumed by the `gokz-top-ljroom` SourceMod plugin
  - `/v1/me/notifications` for authenticated player notification inbox reads, unread counts, and read-state mutations
  - `/v1/me/qq-binding-code` for authenticated short-lived QQ bot binding code generation backed by an admin-managed encrypted shared secret
  - `/v1/player-reports` for authenticated player report submissions with optional record context
  - `/v1/admin/servers` for RBAC-protected server and server-group management
  - `/v1/admin/servers/globalapi/records/export` for owner-scoped, streamed GOKZ LocalDB MySQL record exports across one or more GlobalAPI server IDs
  - `/v1/admin/player-social-links` for superuser management of player social links and verification state
  - `/v1/maps/reviews` supports website-authored review upserts, server-group writes, and QQ-bot writes authenticated by the active QQ binding secret; authenticated comment-only deletion remains available across a player's review rows for a map
  - `/v1/polls` provides public poll browsing and authenticated voting, while `/v1/admin/polls` is restricted to root admins for poll lifecycle management and voter audits
- Data strategy:
  - Backend operators can stream valid records for explicit GlobalAPI server IDs or server groups into a gzip-compressed CSV with `kztop export records`, optionally bounded by inclusive UTC creation dates. The archive retains VNL/SKZ/KZT/NKZ and long map names, excludes invalid rows and non-convertible Steam IDs, and carries both source and GOKZ-local identifiers and runtimes. `kztop export players` exports the corresponding distinct players with alias fallback, permanent-ban flags, and all-server session IP/activity enrichment.
  - GOKZ LocalDB exports translate valid GlobalAPI VNL/SKZ/KZT records into gzip-compressed MySQL scripts for the standard `Players`, `Maps`, `MapCourses`, and `Times` tables. Exports preserve existing player/map rows, append time rows, convert SteamID64 to account IDs, and stream both database reads and gzip output to keep memory bounded for large servers.
- PostgreSQL as primary persistent store
  - Community reactions use a polymorphic `(content_type, content_id)` target key so new reactable resource types do not require nullable target columns; target existence and cleanup are enforced by application workflows because PostgreSQL cannot apply one foreign key across multiple target tables.
  - Map skill analysis is stored in `map_skill`, keyed by map ID, with six aggregate fractions and the ordered analysis segments retained as JSONB. Operators populate it with the manual `python -m app.import_map_skills <index.json>` CLI; normal `/v1/maps` responses expose only the aggregate fractions.
  - Detected LJ-room payloads are stored in `map_lj_room`, keyed by map ID with one opaque JSONB document per map. Operators populate or refresh them with `python -m app.import_lj_rooms <gokz-lj-rooms.json>`; the analyzer export is not bundled with deployments.
  - PostgreSQL-centric derived/cache artifacts (no Redis runtime dependency)
  - Application-wide settings use typed accessors over the `app_setting` key/value table, with JSONB payloads per key. Public settings APIs expose only an explicit safe subset; the encrypted QQ binding secret, community-link placement, and deployment-local GlobalAPI record-sync toggle share this store without exposing arbitrary rows.
  - Ban rows are stored locally in PostgreSQL with an internal UUIDv7 primary key (`ban.uuid`) plus a nullable external GlobalAPI id (`ban.id`), allowing append/update-only mirrored GlobalAPI bans and superuser-created local bans to coexist in the same table
  - Scope-aware leaderboard read models are materialized in PostgreSQL from `record_pb` data and refreshed by a single midnight-UTC rank pipeline plus repair/backfill CLIs
  - `record_pb.raw_rating_contribution` stores the per-PB-row raw rating contribution assigned during player leaderboard rebuilds, so record list APIs can show how each contributing PB feeds the player's raw rating
  - The maps leaderboard is materialized in `cache.map_leaderboard`, keyed by `(map_id, scope)`, derived from raw valid stage-0 `record` rows, and joined with scoped map tiers plus map review summaries at read time
  - `map_course_tier`, keyed by `(course_id, mode)`, is now the v1 source of truth for course and map tier reads; `record_filter` is limited to availability metadata, and tier-bearing responses normalize to integers `0..8` with `0` meaning unavailable, impossible, or unknown
  - Main-map world-record reads are materialized in `cache.map_wrs`, derived from main-course `record_pb` rows, keyed by `(map_id, scope, type)`, and refreshed from record mutation flows
  - Recent main-map WR events are materialized without a retention cap in `cache.recent_wr_events`, keyed by `(record_uuid, scope, type)`, while preserving combined NUB/PRO achievements. The schema-only Alembic migration leaves this cache empty; `python -m app.backfill_recent_wr_events` bootstraps it from current 1000-point `record_pb` winners in resumable, advisory-locked course batches. After bootstrap, record maintenance appends new WR events without deleting superseded valid events; only invalid runs, active bans, and invalidated maps are removed. The dashboard, rather than the database, limits display to the newest 100 cards.
  - Player profile stats are cached in `cache.player_stats`, keyed by `(steamid64, type)`, and now include UTC daily activity, total playtime, grouped most-played-server breakdowns, and top-10 most-played-map breakdowns by record count and record time. Activity and total playtime combine completed sessions with uncovered record time; server/map breakdowns aggregate raw `record` rows. Caches refresh lazily on read after midnight-UTC expiry; most-played-server rebuilds auto-update `player.favorite_server_id` or `player.favorite_server_group_id` unless a manual favorite override action exists
  - Live CS server status uses PostgreSQL as the only shared cache/source of truth for browser reads
  - Player connection sessions are stored in `player_session` from SourceMod plugin events, keyed by plugin-generated UUIDv7 session IDs with PostgreSQL-generated duration seconds
  - Player sessions snapshot GeoIP country/region/city at ingest time for admin-only shared-IP traversal across exact IP, `/24`, and `/16 + city` buckets
  - Player self-service profile edits and rate-limited sync actions are tracked in `player_action_timestamp`, keyed by `(player_steamid64, action)`, with 30-day cooldown rows for `alias_change` and `custom_id_change`, a `country_manual_override` row that disables automatic country refreshes after a manual country change, a `favorite_server_manual_override` row that disables favorite-server auto-updates after any manual favorite choice including `None`, and a one-minute `friends_sync` action used by the player friends sync flow
  - Automatic Steam/GlobalAPI/player-session country refreshes use the absence of a `player_action_timestamp(country_manual_override)` row as the gate for overwriting `player.country`, while manual user/admin country edits remain allowed
  - KZ-only player friendships are stored in `player_friend` as directed edges, with sync flows maintaining both directions for active friendships and deleting stale edges only after a successful Steam friends fetch
  - `player` now persists Steam friends visibility state through `friends_visibility` and `friends_visibility_checked_at`, allowing public profile reads to explain whether a Steam profile or friends list is private without storing generic sync-failure state
  - `player.favorite_server_id` and `player.favorite_server_group_id` persist the resolved favorite server target with a check constraint allowing at most one target; grouped favorites display and link through the server group summary shape
  - Player profile comments are stored in `player_comment`, keyed by UUIDv7 and linked to both author and target `player.steamid64`, with trimmed text validation, reverse-chronological profile reads, and owner-or-author deletion
  - Tournament data is stored in `tournament` with S/A/B/C levels, while player placements are stored in `tournament_achievement`, keyed by UUIDv7 and unique per player/tournament; public profile reads expose awarded placements and superuser-only `/v1/admin/tournaments` manages tournaments and awards
  - Player notifications are stored in `player_notification`, keyed by UUIDv7 with an idempotent `source_key`, recipient/actor Steam IDs, read timestamps, target URLs, and typed payload fields for profile likes, profile comments, follows, and future-only WR-beaten events
  - Player reports are stored in `player_report`, keyed by UUIDv7 with reporter/target Steam IDs, optional record UUID context, and a bounded description; each submission sends `player_report` notifications to active admins, superusers, and the configured root user when present
  - Admin record moderation includes `POST /v1/records/bulk-delete-faster` (`record_uuid`, `scope`, `type` → affected `count`), direct invalidation of raw runs, removal of their derived PB entries, and batched per-record audit snapshots. Individual and bulk admin invalidations do not synchronously rebuild fallback PBs, points, WRs, map summaries, or activity caches; those remain on their existing maintenance paths. `/v1/records/bulk-delete-faster/preview` uses the same selection to return thin run details grouped by player and rendered with `PlayerDisplay`; its snapshot token optionally guards deletion against changed records. Preview and deletion selection share the `ix_record_valid_map_stage_time_uuid` partial index (`map_id`, `stage`, `time`, `uuid`, where `is_valid = true`), built concurrently by migration; selection must use `is_valid = true` rather than `IS TRUE` to remain eligible for the index. Admin valid-to-invalid transitions create transactional, batched `reported_record_invalidated` notifications deduplicated by reporter/record in `player_notification.source_key`.
  - Coverage tracing enables `concurrency = ["greenlet"]` for SQLAlchemy async session execution; omitting it undercounts statements after database awaits.
  - Player social links are stored in `player_social_link` as platform-specific account identifiers, with URLs derived at API/UI edges; Discord supports OAuth-only verified linking using stable user IDs with a ten-minute signed state bound to an HttpOnly callback nonce cookie; Twitch and YouTube support OAuth self-verification, Bilibili supports profile-code self-verification, and admins can still manage verification metadata. The media runner polls verified YouTube and Bilibili upload feeds under one advisory lock; a shared ASCII-boundary classifier persists platform tags and positive KZ eligibility on `media_post`, public reads and view refreshes exclude nonmatches, rejected rows remain available for reclassification during the 90-day retention window, and R2 thumbnail caching is limited to eligible uploads. YouTube canonical snippets are fetched in batches of 50, while Bilibili canonical details are fetched per video and tags are requested only when title/description do not already qualify. Bilibili upload requests use cached WBI signing and may send a server-only dedicated-account `BILIBILI_COOKIE` containing `SESSDATA` to handle anti-bot checks. Operators can re-fetch and reclassify retained rows with `kztop sync media --reclassify-existing`.
  - QQ bot Steam-account binding is stateless on the website side: `/v1/me/qq-binding-code` emits a short-lived 27-character alphanumeric HMAC-signed proof string (`KZTOP` + 22 base62 chars) using the active encrypted `qq_binding_secret` application-setting payload configured by a superuser at `/admin/settings`; the same secret authenticates trusted bot API requests through `X-QQ-Bot-Key`, while the external QQ bot remains the source of truth for QQ-to-Steam bindings
  - Verified Bilibili, YouTube, and Twitch follower counts for community leaderboard display are cached in `cache.player_video_platform_followers`, keyed by `player_social_link.id`, and refreshed lazily with a TTL so public reads do not depend on live platform API success
  - Player-owned Discord webhooks are stored in `player_webhook`, keyed by UUIDv7 and owned by `user.steamid64`, with per-webhook enablement and last-used timestamps
  - Live stream observations are stored in `live_stream_state`, keyed by `player_social_link.id`, and retain the last successful live metadata needed for `/live` offline history cards
  - Cloudflare R2 is available as a reusable S3-compatible object storage integration when `R2_*` settings are configured; staging and production deployments use separate bucket/public-url secrets, live stream polling stores changed Bilibili and Twitch keyframes under immutable UUIDv7 object keys, suppresses duplicate uploads with a persisted SHA-256 hash, and retains the current object reference for online and offline cards. The advisory-locked live runner deletes superseded objects after committing replacements and sweeps unreferenced `live/keyframes/` objects hourly after a 24-hour grace period. The production-only map file distributor uploads BSP, optional BZ2, full `GlobalMaps.7z`, and per-date release ZIP objects there
  - Map file distribution stores long-lived raw BSPs plus the full `GlobalMaps.7z` archive under `MAP_FILE_STORAGE_DIR`, with optional manual seeding from an operator-provided starter package and SteamCMD-based Workshop refreshes for new or updated maps
  - Jumpstats are stored in `jumpstat`, keyed by UUIDv7, with scalar headline metrics plus per-strafe JSONB payloads, a nullable versioned `visualization_data` JSONB cache for replay-derived route samples, server-group-authenticated replay uploads accepted through multipart `POST /v1/jumpstats` and raw `POST /v1/jumpstats/replay`, eligibility pre-checks served by `GET /v1/jumpstats/replay-eligibility`, and public reads served from `/v1/jumpstats`, `/v1/jumpstats/{id}/visualization`, and `/v1/players/{identifier}/jumpstats`
  - Uploaded/imported replay binaries are stored on disk under `REPLAY_STORAGE_DIR`, partitioned by replay type, with jump replays under `jumps/<jumpstat-id>.replay` and run replays under `runs/<normalized-map-name>/<record-uuid>.replay`
  - `gokz-top-replays` discovers legacy and UUID jump replay filenames incrementally and reads upload identity from their headers. Its bundled Linux filesystem helper rejects symlinks, snapshots stable files, and elects one active worker across instances sharing a SourceMod directory, handing ownership off when an instance hibernates. A private SQLite queue and replay spool survive reloads, bind jobs to their original API URL, and retry transient failures without storing keys. First installation starts discovery at activation time; historical recovery is a separate manual API operation.
  - Jump replay retention is per player and mode: the app keeps the best 10 `LJ` replay files and the best replay file for each other supported jump type, while an advisory-locked in-app cleanup runner deletes old non-kept jump replay files after the configured grace period without deleting `jumpstat` rows
  - Historical run replays can be backfilled with the `app.import_run_replays` CLI, which accepts `.replay` files, directories, `.zip` archives, and `.7z` archives, requires v2 `NRM` style, matches exact player/mode/map/stage/time within a 24-hour `record.created_at` window, and skips ambiguous or already-imported replays
  - `/v1` record-shaped responses now expose `is_replay_available`, derived from run replay storage existence by `(map_name, record.uuid)` without changing `/v0` compatibility payloads
- Ranking read models:
  - `leaderboard_player` stores per-scope player aggregates for rating, tier-split rating, total points, WR counts, high-point record counts, and unique validated main-map finishes
  - Each leaderboard player row also stores six raw map-skill ratings derived from virtual PB-point entries. For each skill independently, analyzed main maps are ordered by their unchanged best NUB/PRO PB points with map ID breaking ties; a map portion `w` supplies `w` continuous full-portion entries (`100 * w` atomic entries) at that point value. Each skill retains the highest-point evidence up to `50 / 6 = 8⅓` full-portion entries, truncating the last block continuously. This represents the expected per-skill evidence from 50 evenly distributed six-skill maps. Blocks are evaluated in constant time with a separately configured full-portion decay. The current tune uses `0.90`, giving about 6.58 full skill-portions of half-life so early high-point entries dominate completion breadth; overall rating remains unchanged; easy/hard map caps and display calibration are described below. A versioned NumPy-backed development snapshot under `.temp/skill-rating-tuning/` permits full-population decay comparisons without rescanning PBs. `skill_rating_converter` stores 24 manually calibrated scope/skill display curves, not recomputed on reads or nightly ranking rebuilds. Levels 2–10 retain their strict population-percentile thresholds; a unique observed leader anchors at `10.99999`, tied leaders anchor at `10.99`, and flooring to two displayed decimals shows either as `10.99` while exact 11 remains unattainable. The profile currently renders only a frontend-relative radar: it preserves the strongest skill's global radius while mapping the player's own minimum-to-maximum range inside that footprint, and its adaptive minimum (`25% + 55% × weakest_global_radius`) keeps near-11 skills visually near the outside. Axis labels retain the globally calibrated ratings. The dormant direct global plot calculation is retained for a possible future view but has no current user control. Deployments must explicitly rebuild all four scopes and save all 24 converters after the migration; API reads and nightly rebuilds do not perform calibration.
  - The player leaderboard can sort by any of the six raw skill ratings through one selectable skill column. Each sort has a matching `(scope, skill rating DESC, overall rating DESC, steamid64)` index, while the cell displays the independently converted skill value.
  - `GET /v1/players/compare` combines two public player leaderboard summaries with validated, stage-0 `record_pb` runs, scoped course tiers, per-tier main-map completion totals, and NUB/PRO time and points deltas; it is a read-only derived view rather than persisted comparison data
  - Player leaderboard rebuilds also refresh `record_pb.raw_rating_contribution`, assigning each eligible course's decay-weighted raw rating term to the deterministic best PB row and zeroing non-contributing rows
  - `leaderboard_player` rows only exist for players with at least 10 unique validated main-map finishes in scope and no active mirrored ban; rebuilds delete rows that fall below the threshold or become actively banned
  - `GET /v1/leaderboards/players` reads from `leaderboard_player` with order-specific composite indexes for the supported sort modes and a cached per-scope count read model for shared no-geo totals
  - `GET /v1/leaderboards/community` returns profile-view/like rankings plus the highest cached verified platform follower count among Bilibili, YouTube, and Twitch for each returned player, and supports sorting by `platform_followers`
  - `GET /v1/leaderboards/countries` aggregates eligible unbanned `leaderboard_player` rows by player country and scope, exposing ranked-player and 30-day active-player counts, top-three players, median rating, and top-10 average rating; only countries with at least 10 ranked players receive a competitive rank
  - Active mirrored bans are enforced as query-time exclusions for selected leaderboard and record reads via `EXISTS`/`NOT EXISTS` predicates instead of direct joins
- Live server status subsystem:
  - A2S collection persists the full reported App ID in `server_live_status.app_id`, preferring the extended GameID’s low 24 bits. API and WebSocket live status expose `app_id`; `/servers` shows direct Steam connection only for standalone CS:GO `4465480`, with copy commands available for all servers. Plugin heartbeats preserve identity; `state.last_app_id_query_at` schedules hourly identity probes even with fresh plugin telemetry, and failed probes cannot override fresh plugin online status.
  - `server.is_public` controls public visibility independently from operational `status`; hidden servers continue heartbeat ingestion, discovery, and A2S health collection but are excluded from public lists, detail/history reads, group counts, and WebSocket payloads
  - Public reads come from cached `/v1/servers` and `/v1/servers/{id}` responses only; browsers never trigger upstream A2S or Steam server-list queries
  - Server country/city/latitude/longitude are persisted on `server` rows and resolved only on writes when missing or when the IP changes, preferring online IP location providers before falling back to the local GeoIP database
  - SourceMod server heartbeats are sent by `gokz-top-servers`, which reuses `gokz-top-core` auth config and resolves the target server by cached public IPv4 plus `hostport`
  - SourceMod in-game profile/rating reads are served by `gokz-top-profile`, which preserves the legacy `gokz-profile` library/native surface while reading cached `/v1/leaderboards/players/{identifier}` data through `gokz-top-core`
  - SourceMod LJ-room teleports are served by `gokz-top-ljroom`, which reuses `gokz-top-core` HTTP configuration, fetches `/v1/maps/lj-rooms` at map start, and keeps player default distances in private client cookies
  - Plugin heartbeats ingest through `PUT /v1/servers/status` with a server-group API key and resolve servers by `(ip, port)`
  - Plugin heartbeats also carry cached `gokz-global` GlobalAPI check results; public `/v1/servers` reads expose the per-check and KZT/SKZ/VNL mode results used by the servers-page GlobalAPI badge
  - Plugin heartbeat player payloads are typed and richer than A2S player rows, including GOKZ timer status, mode, teleports, timer time, pause state, stage, and per-connection duration
  - Player session events ingest through `/v1/player-sessions/connect`, `/heartbeat`, and `/disconnect` with `X-Server-Group-Key`; server group identity is derived from the API key rather than request JSON
  - Superuser session investigations use `/v1/admin/player-sessions/ip-links` to traverse shared-IP session buckets with bounded depth and busy-bucket skipping
  - Discovery uses Steam `IGameServersService/GetServerList` across regions `0..7`, with a one-hour background interval and a superuser-triggered manual run endpoint
  - A separate collector process handles Steam server-list discovery, A2S refresh, offline marking, and raw heartbeat partition maintenance
  - WebSocket updates are delivered from `/v1/ws/servers` after cache updates, using PostgreSQL `LISTEN/NOTIFY` to fan out change events from the backend
  - Player displays schedule non-blocking Steam identity refreshes for profiles that have never completed a Steam response or are older than seven days; successful changes fan out through `/v1/ws/players`, while failed Steam requests retry after one hour
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
- coverage (90% minimum enforced by the backend report configuration; data and HTML reports live under `.temp/backend/`, including CI and Docker runs)

## Frontend Runtime and Libraries
- Shared `DataTable` text columns opt into `meta.flexibleWidth` and may set `minSize`; they grow from readable minimums up to 240px, then share the remaining width across metric and date columns. Use `meta.distributeWidth` for columns that should share surplus width while other columns retain their configured size; the players leaderboard caps Player at 240px and distributes the rest across metrics and Last Played. The table calculates a readable minimum width and retains horizontal scrolling on small screens. Full timestamp columns reserve 208px. `PbRecordsTable` applies the same allocation helper (`distributeTableColumnWidths`) through its visible-column colgroup; both renderers use `useTableContainerWidth` to measure available space. Action/replay columns stay compact with `distributeWidth: false` or their explicit narrow widths. Avoid fixed player/server widths or inner text widths that prevent shrinking.
- React 19
- TypeScript 5.9
- Vite 7 + `@vitejs/plugin-react-swc`
- TanStack Router automatic code splitting runs only for production builds. Development serves regular route modules for HMR, avoiding persistent failures of virtual `?tsr-split=component` imports.
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
  - shared `ReactionBar` built from Radix/shadcn Popover and ScrollArea; reaction writes use optimistic local state and public reactor lists use paginated React Query reads
- Generated API client:
  - @hey-api/openapi-ts
  - frontend review authoring flows read both latest-review and website-review variants from the generated `/v1/maps/reviews` contract
  - `/compare` is a URL-backed React route with two player search selectors, profile completion cards, a shared 0–11 skill radar, and sortable/filterable NUB/PRO main-stage comparison tables with shared pagination; query serialization preserves player SteamID64 strings without quotes; authenticated player context menus can open it prefilled with the viewer and selected player

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
- The replay viewer accepts mutually exclusive `replay`, `jump_id`, or public HTTPS `replay_url` deep links. External replay files are downloaded directly by the browser under the provider's CORS policy and still render only against the viewer's host-mounted map resources; there is no server-side external replay proxy.

## External Integrations
- Steam OpenID and Steam Web API integration paths exist in backend flows.
- `/v1/releases` proxies GitHub releases through a five-minute PostgreSQL cache, keeps the latest 20 entries reactable, and serves stale cached entries during temporary GitHub failures.
- GlobalAPI endpoints are consumed for synchronization/compatibility behavior.
- GlobalAPI record-filter sync now mirrors availability rows only, ensures exact 128-tick `map_course` rows for locally known maps, and does not derive non-VNL course tiers from upstream filter data after the one-time backfill migration.
- Twitch Helix API is consumed for verified Twitch live-stream status and cached Twitch follower counts using app credentials.
- Cloudflare R2 can be consumed through its S3-compatible API for app-managed public object storage.
- SteamCMD is used by the production map file distributor to download Workshop map BSPs for app id `730`.
- YouTube Data API can be consumed with `YOUTUBE_API_KEY` to refresh cached YouTube subscriber counts for verified social links, and Google OAuth credentials (`YOUTUBE_CLIENT_ID`/`YOUTUBE_CLIENT_SECRET`) power self-serve YouTube social-link verification. Production media sync also subscribes verified YouTube channels through WebSub; signed upload notifications schedule an immediate idempotent sync while the 15-minute polling runner remains the recovery path. Public `/media` reads include both YouTube and Bilibili uploads and refresh stale platform-specific view counts independently.
- GlobalAPI ban sync upserts by nullable external `ban.id`, uses large backfill pages for catch-up, then incremental `created_since` overlap polling with a steady-state page size of `10`, and ignores local manual bans because they do not carry an external id.

## Implementation Constraints
- Do not hand-edit generated frontend files:
  - `frontend/src/client/*`
  - `frontend/src/routeTree.gen.ts`
- Keep compatibility behavior under `/v0` stable; project-native changes should go to `/v1`.
- Treat 64-bit identifiers such as `steamid64` as strings at all API and frontend boundaries. Do not send them as JavaScript numbers, because precision loss can silently break queries and mutations. Convert to integers only inside backend internals when numeric DB comparisons are required.
- `/v0/bans` remains a mirrored-GlobalAPI compatibility surface and excludes local manual bans, while `/v1/bans` returns both mirrored and local bans, exposes both `uuid` and nullable `id`, supports superuser `POST /v1/bans` manual creation, and uses UUIDs for `/v1/bans/{uuid}` detail reads.
- Use UUIDv7 for new UUID fields/defaults and update touched UUID defaults to UUIDv7 unless compatibility requires otherwise.
- Community reactions use stable allowlisted emoji keys and exactly one nullable target foreign key per row. Summaries must be batch-loaded for collection responses; WR WebSocket payloads remain viewer-neutral.
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

- Discord social-link OAuth uses optional `DISCORD_CLIENT_ID`/`DISCORD_CLIENT_SECRET`, the `identify` scope, and `/v1/social-link-verifications/discord/callback`. Tokens are transient; player URL writes cannot bypass OAuth. Discord links use existing verified-account uniqueness and have no media visibility switch.

## Player setup and product catalog

- Product identities, aliases, and operator audit records live in the dedicated PostgreSQL `products` schema. `public.player_hardware` stores one row per player with an ordered JSONB `selections` array and creation/edit timestamps (multiple disks, singular other categories); `public.player_game_settings` stores DPI and decimal CS:GO sensitivity. eDPI is derived at read time.
- `/v1/products`, `/v1/me/setup`, `/v1/players/{identifier}/setup`, and `/v1/leaderboards/gear` provide the catalog, authenticated setup replacement, profile display, and current usage aggregation. Community products are shared immediately; short catalog/setup writes and merges use a PostgreSQL transaction advisory lock.
- `kztop products` handles versioned imports, verification/correction, and transactional merges. Product names link to a web search; product image hosting and previews are out of scope. `backend/app/data/products.v1.json` records catalog sources and research dates for over 2,400 models across all 13 categories; re-run the idempotent import after catalog updates.
- Alembic reflects only the managed public/cache/products schemas and model tables, leaving externally managed tables and partition children untouched.

- Add-product dialogs explicitly show their fixed gear category and filter suggestions accordingly. Brand choices come from verified canonical catalog products, with an explicit missing-brand fallback. Optional HTTP/HTTPS product URLs are recorded in the existing operator audit log (including duplicate submissions), never fetched; `kztop products references` lists them for review and resolves merged products. No additional database migration is needed.

- Setup product searches dismiss on outside pointer/focus changes. The brands endpoint requires a gear category and lists only verified brands in that category. Custom-product required fields use red asterisks; setup editing omits memory speed and retains existing stored speed when saving a retained memory entry.

- Gear setup uses a category-filtered searchable brand popover with keyboard navigation. Inline product inputs retain selected labels and expose an accessible clear button; configuration controls live with their corresponding gear selectors.

- Product catalog revision 4 contains 2,451 models, retaining the NuPhy/Ryzen/Chinese-market additions and expanding thin GPU, CPU, monitor, PSU, storage, case, and peripheral categories. The versioned products.coverage.v4.json records category counts and complete coverage of 81 explicitly named discrete GPU identifiers in the September 2026 Steam survey main table. Steam is a GPU coverage reference, not an exact CPU/peripheral model source or GOKZ usage ranking. Chinese brand/model aliases and R5/R7 shorthand are seeded; category-scoped curated brands are available after the idempotent operator import.

- Setup replacement supports top-level operating_system stored in player_game_settings and positive storage_capacity_gb in player_hardware (including capacity-only storage). Additive migration 98ea05caeefd introduces nullable columns. Profile setup editing is in the card header, product links omit community badges/underlines, setup-related tabs are last, and the gear leaderboard omits search and descriptive participation text.

- Migration 89e9355f393f preserves storage_capacity_unit (GB/TB, existing entries default GB) alongside integer GB capacity. Editor converts using decimal storage units (1 TB = 1000 GB); public setup respects the saved unit. Points distributions render only on profile Stats via ProfileRecordDistributionSection; gear categories appear as wrapping buttons above the leaderboard table, defaulting to Mouse; the title and category dropdown are removed.


Rating.E uses the best 100 validated main-course maps in tiers 1–4; Rating.H uses the best 50 in tiers 5–8. Each map contributes its higher NUB/PRO PB-point value, with the existing 0.975 weighted decay and ten-map player eligibility. Each category has an independent population-calibrated display curve per scope, using the same percentile and tie rules as skill ratings (maximum displayed value 10.99). Eligible unbanned players with zero category rating remain in the calibration population. Missing curves and zero raw ratings return null.

After changing these limits or the formula, run `kztop build rating` across all scopes, preview `kztop build difficulty-converters`, then explicitly save with `kztop build difficulty-converters --save`. Use `--scope` to select a scope. Reads and nightly rebuilds never refresh these curves automatically. Overall rating, total points, and six-skill ratings are unchanged.

Rating rebuilds process up to 500 players from one scope per transaction. PBs, tiers, map skills, and existing rows are loaded in batches; changed PB contributions are written with a bulk update, and the cached scope count is refreshed once per batch. The calculations match individual live rebuilds. Completed batches remain committed if a run is interrupted; rerunning the same command safely recomputes them. Display-curve calibration remains an explicit separate step.

If a rating batch encounters a PostgreSQL deadlock or serialization conflict, the rebuild rolls back that batch and retries it in a fresh transaction, up to five attempts with exponential backoff and jitter. PB contribution writes use a deterministic player/course/type order. Other database errors and exhausted retries stop the command; already committed batches remain intact.

- `/maps` shares canonical main-course PB query keys with profiles (null stage normalizes to zero), keeps session-long PB caching, and uses the shared NUB/PRO toggle. The Runs WebSocket refreshes profile PBs on every connection, including the initial connection, to reconcile records missed while navigating away. Player-filtered subscriptions serve all profile viewers, including anonymous visitors; record events also invalidate PBs. Map Metrics includes a frontend-derived median-best-time WR gap without new API fields.

## Direct records and replay catalog

- `POST /v1/records/check` and `POST /v1/records` authenticate native servers with existing server-group keys. `PUT /v1/records/{uuid}/globalapi` reconciles exact upstream identities; `PUT /v1/records/{uuid}/replay` accepts qualifying binary replays. Static write routes precede UUID reads. GlobalAPI is optional for native acceptance.
- `record_upload_receipt`, `record_source_claim`, `record_uuid_alias`, and `record_replay` persist idempotency, provenance, reconciliation, and storage metadata. Transaction advisory locks serialize receipts, canonical identities, upstream IDs, and course ranking decisions. Native records retain optional legacy attribution and a native server UUID. Identity-only reconciliation preserves supplied UUIDv7 identifiers, moderation, aliases, and immutable storage keys.
- NKZ run index 3/backend ID 203 shares KZT course eligibility and contributes to KZT/OVR. OVR scope ID 3 must never be interpreted as NKZ. Replay admission is frozen at acceptance: strict PB plus main-course top 50 OVR/top 10 mode, or bonus WR; NUB includes all runs and PRO requires no teleports.
- Normal replay availability, listing, counts, pagination, and R2 redirects use indexed database metadata without R2 LIST/HEAD or filesystem scans. Importers maintain metadata and publish record updates. Explicit bounded `python -m app.record_replay_catalog backfill|reconcile` commands handle historical disk files and rare external changes. Apply autogenerated migrations and backfill before switching reads; enable server uploads afterward. `app.record_identities` inspects/resolves uncertain claims, and `app.record_replay_cors` preserves existing bucket rules while adding viewer origins.
- The separate `gokz-top-records` SourceMod plugin consumes the documented `GOKZTop_GetHTTPConfig` native. Its private SQLite queue and replay spool survive reloads/restarts and retain original API/server identities. Optional AXEKZ UUID natives are feature-detected; stock APIs remain supported. Upstream core/global/anticheat plugins are unchanged. Late-loaded validation requires a fresh map.
- Staging replay disk storage uses the runner's persistent `_replays/<stack>` directory, outside per-run deployment checkouts. This keeps imported disk replays and catalog paths valid across staging redeployments; the container path remains `/app/.replays`.

- Replay header time validation accepts rounding or SourcePawn truncation of the exact stored float to milliseconds; this preserves queued payloads without admitting arbitrary time tolerances.

- Server plugins automatically identify instances using authenticated server SteamID64, following AXEKZ. Group-key heartbeats register identity and track address changes, with unique ownership and preserved internal UUID/history. Records accept SteamIDs or legacy UUIDs and retry pending registration. No operator-set instance ID or per-instance verification is required; group validation and moderation remain enforced.

- `/servers` presents independent GlobalAPI/gokz.top readiness sections; online badges turn green for either eligible service. Authenticated heartbeat `gokz_top_status` carries records-plugin evidence and mode versions, validated by the backend and persisted inside the existing status JSON (no schema migration). Public live status exposes a separate direct status including NKZ/KZT filter sharing. Missing evidence clears readiness.

- In-game PB feedback captures the API baseline on `GOKZ_OnTimerEnd_Post`, independently of local PB processing. `GOKZTop_OnRecordAccepted` wakes bounded refreshes after durable upload acknowledgement; consumers match environment/player/map and distinguish run mode 3 (NKZ) from OVR scope 3. PB time, points and date are read together; cache revisions and finish serials reject stale responses, and environment changes clear comparisons. SourceMod regression probes exercise production handlers without creating runs.

- Direct record acceptance atomically advances player date bounds, rebuilds the submitting player’s applicable leaderboard totals/PB contributions, and invalidates non-daily activity aggregates (including historical cursors). Server receipt time marks record updates so delayed runs remain visible to incremental jobs. Player-filtered OVR events refresh profile metadata on every tab regardless of selected scope. Bounded `python -m app.record_player_metadata [--apply] --limit N --after STEAMID` repairs previously accepted native players without changing identity fields or emitting runs.

- Records plugin 1.0.1 persists environment/map-specific exact 128-tick NUB/PRO course filters in its existing SQLite database, refreshing from gokz.top every minute. NKZ reuses KZT bits. Known unsupported finishes never enter the queue; unknown metadata waits durably in `filters` without uploading. The worker rechecks before uploads and prunes unsupported unacknowledged/rejected jobs and only their private replay copies. Backend filter rejection revokes stale positive cache entries; acknowledged jobs and other failures retain their previous behavior.

- Replay downloads in the viewer resolve `/v1/replays/{record_uuid}/url` using catalog metadata, then fetch R2 directly without credentials. This avoids the opaque `Origin: null` caused by API-to-R2 redirects while preserving explicit bucket viewer origins; legacy binary links and disk downloads remain compatible.

- Map name pronunciations use backend-only ElevenLabs Lauren (`DODLEQrClDo8wCz460ld`), Eleven v4, and immutable R2 MP3 clips. Persistent per-map jobs generate existing maps on first playback and queue newly imported maps atomically, with advisory-locked processing, bounded retries, and credential/credit pause recovery. Public GET/POST `/v1/maps/{map_id}/pronunciation` expose status and ready URLs; shared map menus and the map detail title provide single-stream playback. Spoken names omit known prefixes, underscores, and technical suffixes while preserving `final`/numbered final tokens. No catalog backfill or frontend provider credentials.


- Player pronunciation uses the current stored alias/name with Unicode cleanup and on-demand generation only. Maps and players share one provider-locked worker, pause state, audio controller, and R2 storage pipeline. Public `/v1/players/{identifier}/pronunciation` never refreshes Steam. Admin/superuser pronunciation dialogs support voice, automatic/explicit language, and custom speech text; map admins are restricted to maps. Persistent per-target overrides survive normal playback and reset after a cleaned source-name change. `/v1/admin/pronunciations/options` reads cached backend-only provider choices; synthesis model selection remains operational configuration, not an editor control.

- Player setup migration `30fd121073fa` preserves existing selections in JSONB, supports multiple disks and decimal monitor sizes in inches, and tracks setup creation/edit times in the database only (legacy baseline is migration time); these timestamps are excluded from setup API responses and UI. Setup responses keep the hardware array contract. Storage rankings and operator usage counts deduplicate by player/product, with distinct category participants as denominator. Profile setup uses compact rows, Monitor/Mouse/Mouse Pad/Keyboard/Headset order, and CS:GO settings under Peripherals.

- The official QQ bot supports GOKZ only (OVR/KZT/SKZ/VNL). Game-selection commands and CS2KZ integrations are removed. Startup Alembic migrations upgrade the bot’s SQLite user table while preserving Steam bindings and GOKZ preferences.

- Map leaderboard caches expose nullable `median_first_finish_time` for chronological first finishes, separate from the legacy median-of-player-bests field. Cache builds select the earliest valid scoped main-course run per player by `(created_at, uuid)`. Migration `7dcc02da9296` adds the column; `kztop rebuild maps` backfills existing rows. UI WR gaps use run-time/WR multipliers, truncated to two decimals through 10x and one above 10x, while distribution API bins and chart geometry retain logarithmic coordinates.

- Direct records and GlobalAPI sync acquire course locks before player rows/upstream identities, bound lock waits to five seconds, and retry transient direct transactions through durable receipts. Steam fetches, replay request streams and R2 writes release pooled connections during network I/O; replay catalog acknowledgement revalidates eligibility/checksums. Existing records plugins can deduplicate via unique same-group, same-statistics, five-second matches with receipt-capped future clocks and the legacy ±1 ms runtime difference. When a client clock is more than five seconds ahead of receipt time, queued delivery may match upstream timestamps from 30 seconds before receipt through five seconds after it, requiring runtime >35 seconds and bidirectional uniqueness. Ordinary runs <=10 seconds, longer delays, and ambiguous/historical pairs require explicit identity. Both ingestion orders preserve native UUIDs, original receipts, aliases, moderation and replay keys without duplicate notifications. Bounded `app.record_identities --reconcile-compatible [--apply] --limit N --after RECEIPT_UUID` repairs existing pairs. Records plugin1.0.2 reads GlobalAPI `record_id` and follows its full-float serialization/millisecond truncation.

- Server-group API-key usage stamps commit at the authentication boundary before business writes and skip administratively locked rows. This prevents a shared key from serializing heartbeat, record, replay, jumpstat, and map-review requests behind a slow ingest transaction.

- The uploader and PB announcement core share `GOKZTop_FormatRecordTime`; upgrade them together to align accepted-time acknowledgements, new-PB detection and fresh point gains with GlobalAPI millisecond truncation.

- Identity attachment and GlobalAPI sync use non-blocking initial course locks and retry whole transactions after releasing pooled connections. Exhausted attachment retries and pool exhaustion return 503 with Retry-After; busy upstream records defer without advancing their cursor. Compatibility accepts ±1 ms in either direction, checks each direction’s full candidate range, and preserves ambiguity guards, supplied UUIDs, aliases, receipts, moderation, replay metadata, and PB precision.

- Replay eligibility predicates use `Record.is_valid == true()` to match the record table’s partial indexes; `IS true` prevents those indexes from satisfying the query and causes long full-table scans while holding the course lock.

- Frozen replay-policy alternatives for late upstream claims use each candidate’s canonical runtime and the symmetric ±1 ms candidate range, preserving strict PB/WR rules across either rounding direction.

- PB bucket winner selection and map leaderboard refreshes use the same literal `is_valid = true` partial-index predicate as replay qualification. A database-plan regression exercises both write refresh paths and requires partial course indexes.

- `/maps` provides browser-local named presets (up to 20) for scope, NUB/PRO, catalog filters, sorting, and card options; applying resets pagination to page one. Presets are independent of profile Runs and use validated, versioned localStorage with save-error feedback.

- `/maps` and profile Runs independently save optional browser-local default-view snapshots from their Presets menus. Validated versioned defaults load on mount; maps defaults supersede session state and restore scope/card options from page one. Clearing removes only the default, and Runs defaults never activate first-completion history reads.

- Profile Activity and total playtime share versioned daily cache data combining merged completed player sessions and record runtimes whose finish timestamps fall outside those sessions (inclusive endpoints). Sessions split at UTC midnight; open sessions are excluded until disconnect/timeout. Daily entries retain record counts and add total_seconds. Session closure invalidates the shared cache; record mutations refresh affected days. Calendar colors use view-relative positive-duration quartiles. Server/map breakdowns remain record-based.

## Shared QQ and Discord Bot

- The `qqbot/` submodule runs one NoneBot application with independently configurable QQ and Discord adapters. A shared Alconna catalog defines commands, aliases, help, QQ command panels, and Discord slash options; shared services return platform-independent results for Chinese QQ Markdown/keyboards and English Discord embeds/buttons.
- Both platforms verify the existing website-issued `KZTOP` binding codes locally with `QQ_BOT_SECRET`; no new website endpoint or deployment is needed. Discord bindings/preferences use `bot_platform_preferences`, keyed by `discord:<user-id>`, while existing QQ rows are preserved. Daily picks remain independent across platforms. The website's Discord social-link verification is separate.
- SQLite upgrades run transactionally before ancillary table initialization. Deployment backs up SQLite and records the previous image, then checks both adapter connections. Discord omits automatic voice compliments. The existing image name, Compose project, service, and persistent SQLite path remain unchanged.
