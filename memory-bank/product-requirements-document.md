# GOKZ Top v2 - Product Requirements Document (Simple)

Date: 2026-03-11
Owner: GOKZ TOP v2
Status: Draft

## 0) Terminology (Avoid Confusion)
- `gokz-top-v1` means the old project at `/Users/cinyan10/Code/kzcharm/gokz-top`.
- `/v1` routers in this repository are API namespace versions, not the old project.

## 1) Product Vision
GOKZ Top v2 is the all-in-one third-party website for the GOKZ community.

It should fully cover all product capabilities from `gokz-top-v1` (old project), while improving:
- code quality
- modularity and maintainability
- async performance
- frontend design and experience

## 2) Product Goals
- Match and then exceed `gokz-top-v1` functionality (v2 is a strict functional superset).
- Be fully compatible with GlobalAPI-v2 endpoints under `/v0`.
- Introduce better architecture for long-term maintainability and safe iteration.
- Provide fast, reliable, async-first data processing and APIs.
- Deliver a premium player-facing experience centered around profiles, records, and rankings.

## 3) Non-Goals
- Re-creating `gokz-top-v1` code structure or technical debt.
- Breaking endpoint compatibility for consumers that depend on GlobalAPI-v2 behavior.
- Shipping features that have no clear path to maintainability.

## 4) Core Product Scope (Must Have)
`gokz-top-v2` must include everything already existing in `gokz-top-v1` (old project), plus improvements.

### 4.1 Player Ratings and Leaderboard
- Scope-aware player ratings, map-top rankings, and points.
- Global and filterable leaderboards (scope, region/country, periods where applicable).
- Rank lookup and leaderboard slices for profile and map views.
- Users can always switch to mode-only scopes when they want a strictly fair same-mode comparison.

### 4.1.1 Scope Model (Explicit)
- `KZT` scope = `KZT + NKZ`.
- `ALL` scope = all supported modes.
- `SKZ` scope = `SKZ` only.
- `VNL` scope = `VNL` only.

Notice on `NKZ`:
- `NKZ` is a modified/newer variant of `KZT` (currently without perfs) and is relatively new.
- Because of that, `NKZ` does not have a standalone scope in v2 for now; it is included inside `KZT` scope.

### 4.1.2 Scope Product Intent
- Cross-mode comparison is intentional to increase competition and activity.
- `SKZ` players should be able to compete in broader scope leaderboards (especially against the larger `KZT` player base).
- Mode-only scopes remain available so players can switch back at any time.

### 4.2 Records and Map Top
- Record ingestion, querying, and ranking views.
- Map top pages by scope/filter context.
- World-record and recent-record experiences.
- `scope` is required for rank/points-oriented record queries (for example `records/top`, `records/pb`).
- Non-points record queries can omit `scope` when ranking/points context is not needed.
- Points are scope-based; the same record can have different point values under different scopes.

### 4.3 Server Live Status
- Server registry and ownership/admin flows.
- Live status ingestion and cache strategy.
- Public live server status pages and filtering.

### 4.4 Maps and Map Reviews
- Map catalog with filters and metadata.
- Map detail pages with records context.
- Map review and rating workflows.

### 4.5 Player Profile and Stats (Signature Feature)
- Rich profile header (identity, rank, scope preferences, highlights).
- Records summary and personal progression sections.
- Ratings/points trends and map performance breakdowns.
- Jumpstats highlights and replay highlights.
- Social/shareable profile UX with desktop-first design, while keeping mobile clearly usable.

### 4.6 Saving and Presenting Player Settings
- Persist player settings and preference presets.
- Show settings in profile context.
- Support export/backup-ready structure for player-owned config data.

### 4.7 Jumpstats
- Submit, ingest, and query jumpstats.
- Top jumpstats views and per-player jumpstats history.

### 4.8 Replay Uploading
- Upload, store, and retrieve replay artifacts.
- Replay metadata indexing for profile/map/record pages.

### 4.9 Cloudflare R2 Integration
- Use R2 for replay storage and backup artifacts.
- Use R2 for player file/settings storage where applicable.
- Support backup and restore workflows for critical files.

## 5) GlobalAPI Compatibility and Mirror & Extend Pattern
GlobalAPI remains in production and is the source of truth today. `gokz-top-v2` must fetch and mirror key data (maps, records, record_filters, bans) and remain ready to replicate GlobalAPI if needed.

### 5.1 Mirror Rules
- Keep mirrored entities synchronized from GlobalAPI.
- Preserve source identity and compatibility fields needed by existing clients.
- Track sync state and lag per entity type.

### 5.2 Extend Rules
- Build v2-only features on top of mirrored data (for example rating algorithm improvements, custom points logic, richer profile analytics).
- Keep mirrored raw data and derived data clearly separated in schema and service boundaries.
- Keep scope-aware derived rankings (ratings/map top/points) as `gokz-top-v2`-owned computed views, separate from mirrored source data.
- Treat points as scope-dependent derived values, not globally fixed values.

### 5.3 Compatibility Contract
- Provide fully compatible GlobalAPI-v2 style endpoints under `/v0`.
- Treat `/v0` as a stable contract for client compatibility.
- Add contract tests to prevent breaking response fields and semantics.

### 5.4 Replication Readiness
- Design ingestion and storage so v2 can continue operating if GlobalAPI becomes unavailable.
- Define fallback operation mode for sync interruptions and recovery.

## 6) Engineering Requirements

### 6.1 Code Quality
- Clear domain boundaries and reusable modules.
- Strict typing and linting for backend and frontend.
- Test coverage standards maintained (backend coverage target at or above 90%).

### 6.2 Modularity and Maintainability
- Backend organized by bounded contexts (for example: mirror/sync, records, ratings, maps, profiles, servers, jumpstats, replays).
- Minimize cross-module coupling through explicit interfaces.
- Keep compatibility adapters (`/v0`) isolated from internal domain models.

### 6.3 Async and Performance
- Async-first APIs, DB access, and external calls.
- Background jobs for sync and heavy recomputation.
- No blocking I/O on request-critical paths.

### 6.4 Reliability and Observability
- Sync job monitoring (success/failure/lag metrics).
- Basic auditability for critical data changes.
- Health and readiness checks for API and workers.

## 7) Frontend Requirements (Profile Experience First)
- Create a premium profile page that is both visually polished and information-dense.
- Prioritize fast load and smooth interaction on desktop and mobile.
- Provide clear data hierarchy: highlights first, details second, deep analytics third.
- Ensure profile sections are modular so features can be added without redesigning the whole page.

## 8) Milestones (High Level)
1. Foundation + Mirror Core
- Set up stable sync for maps, records, record_filters, bans.
- Provide baseline `/v0` compatibility for core entities.

2. Core Feature Parity
- Reach functional parity with `gokz-top-v1` across records, leaderboards, maps, servers, profiles, settings, jumpstats, and replays.

3. Profile Upgrade + Custom Intelligence
- Launch upgraded profile UX and custom rating/analytics extensions.

4. Replication Hardening
- Validate fallback operation and replication readiness if GlobalAPI is down.

## 9) Acceptance Criteria
- `gokz-top-v2` implements all `gokz-top-v1` user-facing capabilities.
- `/v0` endpoints are compatible with GlobalAPI-v2 consumers.
- Core sync flows for maps/records/record_filters/bans run reliably with observable status.
- Ratings, map top, and points are scope-aware with explicit support for `KZT`, `ALL`, `SKZ`, and `VNL`.
- Users can switch between broader cross-mode scopes and mode-only scopes.
- Rank/points-oriented record queries (for example `records/top`, `records/pb`) require `scope`, while neutral record queries do not.
- Points output is correct for the requested scope.
- Profile page is clearly more useful and more attractive than `gokz-top-v1`.
- Architecture supports independent iteration of compatibility layer and v2-native features.
