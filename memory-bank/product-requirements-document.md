# Product Requirements Document - GOKZ.TOP v2

- Status: Draft
- Owner: gokz-top-v2 team
- Last Updated: 2026-04-04
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
- Public player leaderboard is now available at `/v1/leaderboards/players` with scope switching, server-side sorting, pagination, and metric-specific visibility rules.
- Global and filtered leaderboards (scope, geography, and period when applicable).
- Rank lookup support for profile and map contexts.
- Current leaderboard eligibility rule:
  - rating fields only become non-zero after 20 unique validated main-map finishes in the selected scope
  - players with other useful aggregates may still exist in leaderboard read models, while the API filters rows to positive values for the active sort metric

Scope model:
- `KZT` scope = `KZT + NKZ`.
- `ALL` scope = all supported modes.
- `SKZ` scope = `SKZ` only.
- `VNL` scope = `VNL` only.
- `NKZ` currently has no standalone scope and is included under `KZT`.

### 5.2 Records and Map Top
- Record ingestion and retrieval flows.
- Map top views with scope-aware rank and points context.
- World-record and recent-record experiences.
- Scope-dependent points for rank-oriented queries.

### 5.3 Maps and Reviews
- Map catalog and detail pages with filters and metadata.
- Map review/rating flows.
- Tight linkage between map pages and relevant record context.

### 5.4 Player Profile Experience
- Rich profile overview (identity, ranking highlights, competitive summary).
- Historical performance slices (records, jumpstats, replays, trend-oriented data).
- Shareable, fast-loading profile UI with clear information hierarchy.

### 5.5 Servers and Live Status
- Public server registry and ownership-aware management.
- Live status ingestion and display.
- Server group support and filterable browsing.
- Cached live status must be served from PostgreSQL-backed cache rows, not live upstream queries on page load.
- Support richer plugin heartbeats keyed by server-group API keys, with A2S polling and Steam server-list discovery as collector-side inputs.
- Preserve last-known server identity fields when a server goes offline so players can still see which server is down.

### 5.6 Jumpstats and Replays
- Jumpstats submission/query/top views.
- Replay upload, indexing, and retrieval.
- Replay visibility integrated into player and map workflows.

### 5.7 Auth, Roles, and Settings
- User auth/session flows and API key support.
- Role-based access for admin/operator capabilities.
- Player preferences/settings persistence.

## 6) Compatibility Strategy (Mirror + Extend)

### 6.1 Mirror Rules
- Mirror authoritative entities from GlobalAPI where required (for example maps/records/filters/bans).
- Preserve compatibility-critical identifiers and field semantics.
- Track sync status/lag for reliability and troubleshooting.

### 6.2 Extend Rules
- Keep mirrored source data separate from v2-derived data.
- Build v2-native features (ratings/profile analytics/cache views) on top of mirrored data.
- Keep scope-aware points/rank calculations as v2-owned derived logic.

### 6.3 Contract Rules
- `/v0` is the compatibility contract and must remain stable.
- Compatibility tests guard response shape and behavioral parity.
- New product-native behavior should prefer `/v1` instead of changing `/v0` semantics.

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
