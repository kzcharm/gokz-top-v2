# Product Requirements Document - GOKZ.TOP v2

- Status: Draft
- Owner: gokz-top-v2 team
- Last Updated: 2026-05-07
- Related Docs:
  - `memory-bank/gokz-top-v1.md`
  - `memory-bank/gokz-top-v2-prd.md`
  - `memory-bank/tech-stack.md`

## 0) Terminology
- `gokz-top-v1` refers to the old repository/project (`/Users/cinyan10/Code/kzcharm/gokz-top`).
- `/v0` in this repository is the GlobalAPI v2.0 compatibility surface.
- `/v1` in this repository is the project-native API namespace.

## 1) Product Vision
Build the long-term platform for the GOKZ ecosystem:
- Preserve ecosystem compatibility for existing GlobalAPI consumers.
- Reach full user-facing parity with `gokz-top-v1`.
- Provide a better player product (profiles, rankings, map context, live server visibility).
- Support faster and safer iteration through a cleaner architecture.

## 2) Product Goals
- Maintain strict compatibility behavior for in-scope GlobalAPI v2.0 endpoints under `/v0`.
- Deliver v2 as a functional superset of `gokz-top-v1` for core user workflows.
- Move the system to async-first backend patterns and type-safe contracts.
- Improve profile, leaderboard, and analytics experiences for competitive players.
- Keep operations simple with PostgreSQL-centered persistence and cache strategy.

## 3) Non-Goals (Current Phase)
- Reproduce legacy technical debt or old code structure.
- Break existing third-party integrations that depend on GlobalAPI-compatible behavior.
- Add low-value features that increase long-term maintenance burden.

## 4) Primary Users
- Players browsing profiles, records, and leaderboards.
- Server operators pushing status/events and managing ownership flows.
- Third-party developers relying on stable API behavior.
- Admin/operators managing content integrity and synchronization health.

## 5) Core Product Scope

### 5.1 Competitive Data and Rankings
- Player ratings, points, and rankings with scope-aware calculations.
- Public player leaderboard is now available at `/v1/leaderboards/players` with scope switching, server-side sorting, pagination, and eligibility-based membership semantics.
- Public maps leaderboard is now available inside the `/leaderboards` page `Maps` tab, backed by `/v1/leaderboards/maps`, with scope switching, full validated-map reads, and client-side sorting/filtering for record-derived map metrics plus review summary fields.
- Global and filtered leaderboards (scope, geography, and period when applicable).
- Rank lookup support for profile and map contexts.
- Daily rank maintenance runs as one midnight-UTC pipeline over the previous UTC day's changed `record_pb` rows, rebuilding touched PB point buckets first, then touched leaderboard rows, then touched maps leaderboard rows selected from `Record.updated_at`, then touched Steam-backed player profiles.
- Current leaderboard eligibility rule:
  - players only remain in `leaderboard_player` after 10 unique validated main-map finishes in the selected scope
  - actively banned players are removed from `leaderboard_player`
  - leaderboard membership therefore consists only of eligible, unbanned rows in the selected scope
  - exact leaderboard counts are shared across sort modes for the same scope/geography slice, with scope-wide no-geo totals served from a cached count read model

Scope model:
- `KZT` scope = `KZT + NKZ`.
- `ALL` scope = all supported modes.
- `SKZ` scope = `SKZ` only.
- `VNL` scope = `VNL` only.
- `NKZ` currently has no standalone scope and is included under `KZT`.

### 5.2 Records and Map Top
- Record ingestion and retrieval flows.
- Map top views with scope-aware rank and points context.
- Main-map world-record reads are served from a PostgreSQL cache/read model derived from main-course PB rows and keyed by scope and NUB/PRO record type.
- World-record and recent-record experiences.
- Scope-dependent points for rank-oriented queries.
- Selected leaderboard and record list surfaces exclude players with any active mirrored ban by default, while recent feeds and record detail views remain unchanged.

### 5.3 Maps and Reviews
- Map catalog and detail pages with filters and metadata.
- Map review/rating flows.
- Authenticated players can author website reviews only after earning a main-stage OVR PB on the map.
- Map review authoring must prefill from the player's latest review on that map, while normal website saves continue to target the website review row only.
- Players can delete all of their review comments for a map without deleting any rating rows; this applies across website and server-group review rows.
- Tight linkage between map pages and relevant record context.

### 5.4 Player Profile Experience
- Rich profile overview (identity, ranking highlights, competitive summary).
- Player profiles show linked X, Bilibili, YouTube, GitHub, and Twitch accounts from v2-native social-link records, with unverified links visible but marked.
- `/live` lists player-centric verified stream cards sourced from verified Bilibili and Twitch links, with filters for live versus previously streamed players.
- Offline `/live` cards must show the most recently observed stream across a player's enabled platforms, so future multi-platform support can prefer the newest Twitch/YouTube/Bilibili activity rather than a fixed platform order.
- Historical performance slices (records, jumpstats, replays, trend-oriented data).
- Profile views now consume a consolidated player stats endpoint backed by lazily refreshed PostgreSQL cache rows, with UTC daily activity and total playtime available on the profile.
- Shareable, fast-loading profile UI with clear information hierarchy.

### 5.5 Servers and Live Status
- Public server registry and ownership-aware management.
- Admin server management provides Root Admin access to all GlobalAPI/public servers and Server Owner access to owned servers, with approval control reserved for Root Admins.
- Root Admins can investigate possible alternate accounts from player-session IP evidence using bounded exact-IP, `/24`, or `/16 + city` traversal; the workflow returns explainable links and skipped busy buckets, not scores or automated enforcement.
- Live status ingestion and display.
- Server group support and filterable browsing.
- Cached live status must be served from PostgreSQL-backed cache rows, not live upstream queries on page load.
- Support richer plugin heartbeats keyed by server-group API keys, with A2S polling and Steam server-list discovery as collector-side inputs.
- SourceMod plugins can submit player connection sessions via authenticated `/v1/player-sessions` connect, heartbeat, and disconnect events for playtime, activity, map-time, and shared-IP analytics.
- Open player sessions are closed automatically after heartbeat timeout using the last known heartbeat as the disconnect timestamp.
- Preserve last-known server identity fields when a server goes offline so players can still see which server is down.

### 5.6 Jumpstats and Replays
- Jumpstats submission/query/top views.
- Replay upload, indexing, and retrieval.
- Replay visibility integrated into player and map workflows.

### 5.7 Auth, Roles, and Settings
- User auth/session flows and API key support.
- Role-based access for admin/operator capabilities.
- Player preferences/settings persistence.
- Authenticated players can self-edit `alias` and `custom_id` from `/settings`, with independent 30-day cooldowns and no cooldown consumption for no-op submissions.
- Authenticated players can manually set `country` from `/settings`; manual country changes disable later automatic GeoIP/Steam overwrites but do not block later manual country edits.
- `name` remains read-only in settings because it is synced from Steam rather than edited locally.
- Authenticated players can manage their own social links from settings; superusers can view, add, edit, delete, and verify player social links from admin.
- Authenticated players can manage Discord webhooks from `/settings`; enabled webhooks currently receive all supported stream-start events for the player's verified Twitch and Bilibili links, and players can send a test notification on demand.

## 6) Compatibility Strategy (Mirror + Extend)

### 6.1 Mirror Rules
- Mirror authoritative entities from GlobalAPI where required (for example maps/records/filters/bans).
- Preserve compatibility-critical identifiers and field semantics.
- Track sync status/lag for reliability and troubleshooting.
- GlobalAPI bans are mirrored as append/update-only rows keyed by upstream `id`; if upstream ever introduces true ban deletions/unbans, the sync policy must be revisited.

### 6.2 Extend Rules
- Keep mirrored source data separate from v2-derived data.
- Build v2-native features (ratings/profile analytics/cache views) on top of mirrored data.
- Keep scope-aware points/rank calculations as v2-owned derived logic.

### 6.3 Contract Rules
- `/v0` is the compatibility contract and must remain stable.
- Compatibility tests guard response shape and behavioral parity.
- New product-native behavior should prefer `/v1` instead of changing `/v0` semantics.
- Bans now have both `/v0/bans` compatibility reads and `/v1/bans` public `{data, count}` reads for future user-facing bans pages.
- `/v1/graphql` is an additive read-only player query surface for selective frontend hydration; it does not replace `/v0` and does not remove dedicated `/v1/players*` endpoints.
- Touched `/v1` non-player responses should embed compact player references instead of full player payloads when only identity/display name is required inline.

## 7) Engineering Requirements
- Async-first API, DB, and outbound integrations for request paths.
- Strong typing and lint/test gates across backend and frontend.
- Backend coverage target remains >= 90%.
- Clear domain boundaries (sync/mirror, records, rankings, players, maps, servers, auth).
- Health/readiness surfaces for API and background workloads.
- Auditable and observable sync/ingestion behavior.

## 8) UX Requirements
- Profile-first product quality bar: information-dense but readable.
- Desktop and mobile support with predictable interactions.
- High-value workflows must be quick: search player, inspect profile, compare rank, open map context, view live server state.

## 9) Milestones
1. Core compatibility foundation
- Stabilize `/v0` parity for core public entities.
- Add compatibility test coverage for critical routes.

2. Functional parity
- Match `gokz-top-v1` user-visible capabilities across maps, records, players, leaderboards, servers, and settings.

3. Product upgrade
- Improve profile and leaderboard UX with richer derived analytics.

4. Hardening
- Improve sync reliability, observability, and fallback behavior when upstream sync is degraded.

## 10) Acceptance Criteria
- In-scope `/v0` endpoints are behavior-compatible for existing consumers.
- v2 supports all core user-facing workflows currently expected from `gokz-top-v1`.
- Scope-aware ranking/points behavior is deterministic and documented.
- Sync and ingestion jobs are observable and recoverable.
- Backend CI quality gates remain green, including coverage threshold.
