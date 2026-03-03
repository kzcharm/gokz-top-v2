# Product Requirements Document — GOKZ.TOP-V2 / GlobalAPI-Compatible Rewrite

- Status: Draft
- Owner: gokz-top-v2 team
- Last Updated: 2026-02-27
- References:
  - [gokz-top-v1.md](/Users/cinyan10/Code/kzcharm/gokz-top-v2/info/gokz-top-v1.md)
  - [GlobalAPI.md](/Users/cinyan10/Code/kzcharm/gokz-top-v2/info/GlobalAPI.md)

## Summary

This PRD defines the rewrite of GOKZ.TOP-V1 into GOKZ.TOP-V2 with strict GlobalAPI public `v2` contract compatibility and an upgraded `v3` surface for richer product features.

Locked decisions:
- Scope: Public APIs first.
- Compatibility: Strict contract compatibility with GlobalAPI `v2` public endpoints.
- Upgrade path: New `/api/v3/*` for richer contracts.
- Data and cache strategy: PostgreSQL-only (no Redis dependency).

## 1. Problem Statement

Current gaps:
- The existing backend is template-like and does not yet implement GlobalAPI domain parity.
- V1 has broad product functionality but does not formalize strict GlobalAPI-compatible API contracts.
- Existing consumers need stability while product teams need room for richer contracts and analytics.

Problem to solve:
- Build one platform that preserves compatibility for existing consumers and enables improved product capabilities without breaking established integrations.

## 2. Goals

- Deliver GlobalAPI-compatible public endpoints on `api/v2/*` with strict path/query/response/status parity.
- Rebuild the core stack on FastAPI + PostgreSQL using typed contracts and OpenAPI generation.
- Deliver upgraded endpoints on `api/v3/*` for richer analytics and product-facing use cases.
- Keep the dependency surface minimal by using PostgreSQL for both canonical persistence and cache artifacts.

## 3. Non-Goals (Phase 1)

- GlobalAPI admin parity (`/api/v2/admin/*`) in the first release.
- Full portal/admin UI parity in the first release.
- Any Redis runtime dependency for cache, queue, or rate limiting.

## 4. Users and Consumers

- Game servers submitting records/jumpstats/bans via API key authentication.
- Third-party applications consuming GlobalAPI-compatible public endpoints.
- First-party web clients consuming richer `v3` endpoints.

## 5. API Contract Strategy

| Area | Decision |
| --- | --- |
| Compatibility base | `api/v2/*` |
| Contract strictness | Match paths, query keys, response shapes, and status behavior for public endpoints |
| Extension mechanism | New richer contracts under `api/v3/*` |
| Breaking changes | Not allowed on `v2`; only additive optional fields permitted when proven safe |

Contract policy:
- `v2` acts as a compatibility API and must remain behavior-stable.
- `v3` is the innovation API and may evolve independently with explicit version notes.

## 6. Phase 1 Endpoint Scope (`v2` Public Parity)

In-scope parity requirements:
- `GET /auth/status`
- Records public endpoints (including top, place, recent top, world record counts, and record lookup where applicable)
- Replay public endpoints (upload/retrieve/list), including large payload behavior parity
- Record filters and player rank endpoints
- Bans public endpoints
- Jumpstats public endpoints
- Players public endpoints
- Maps/modes/servers public endpoints, including ownership/apply flows defined as public in GlobalAPI

Out of scope in Phase 1:
- `api/v2/admin/*`

Parity requirement details:
- Path and query parameter names must match GlobalAPI `v2`.
- Response field names and types must match expected compatibility fixtures.
- Status code behavior for success/failure classes must match `v2` expectations.

## 7. New `v3` Endpoint Additions (Upgraded Contracts)

Define first-class upgraded endpoint families:
- `GET /api/v3/leaderboards/*`
- `GET /api/v3/players/{steamid}/profile`
- `GET /api/v3/players/{steamid}/recap`
- `GET /api/v3/maps/{id}/summary`
- `GET /api/v3/servers/status`
- `GET /api/v3/search`

Each `v3` endpoint must explicitly document:
- Added fields compared to `v2`.
- Aggregation/caching source (core table, materialized view, or cache table).
- Response-time budget (p95 target per endpoint family).

## 8. Data and Storage Architecture (PostgreSQL-Only)

Schema strategy:
- `core` schema: canonical transactional tables and relations.
- `cache` schema: derived artifacts optimized for query latency.
- `identity` schema: users, roles, auth tokens, API-key metadata.

Cache mechanisms:
- `UNLOGGED` cache tables for high-churn and rebuildable data.
- Materialized views for heavy read patterns (rankings/distributions).
- Postgres-native refresh and invalidation:
  - `NOTIFY/LISTEN`
  - job tables and worker polling
  - scheduled refresh workers
- Cold-start rebuild rules for crash/restart scenarios.

Critical compatibility rule:
- Serialize 64-bit identifiers safely in JSON (string representation where needed) to avoid JavaScript precision loss.

## 9. Auth and Security Requirements

- API key auth via `X-ApiKey` for server-origin write operations.
- JWT bearer auth for user-bound operations.
- Role gates equivalent to GlobalAPI public behavior requirements.
- Rate limiting implemented without Redis using PostgreSQL-backed rolling window or token bucket tables.
- Security logging for authentication failures and suspicious request patterns.

## 10. Performance and Reliability Requirements

- `v2` read endpoints: p95 latency `<= 250ms` under agreed baseline load.
- `v2` write endpoints: p95 latency `<= 400ms`.
- Cache rebuild after restart: critical derived datasets ready within `<= 5 minutes`.
- Public API availability target: `>= 99.5%` monthly.
- Replay upload max payload and timeout behavior documented and parity-tested.

Reliability expectations:
- Cache rebuild processes are idempotent.
- Health endpoints expose cache readiness state.
- Background workers must fail safely and retry with bounded backoff.

## 11. Migration and Rollout Plan

1. Contract inventory and fixture capture for all in-scope `v2` public endpoints.
2. PostgreSQL schema design and migration baseline.
3. Implement `v2` read endpoint parity.
4. Implement `v2` write endpoints and replay flows.
5. Implement `v3` upgraded endpoints.
6. Hardening, performance tuning, and production cutover.
7. Create Phase 2 addendum for admin parity planning.

Rollout rules:
- No consumer migration is required for existing `v2` clients.
- `v3` adoption is opt-in and documented per endpoint.

## 12. Test and Acceptance Criteria

| Test Category | Required Scenarios |
| --- | --- |
| Contract tests | Snapshot compare `v2` responses against GlobalAPI-compatible fixtures for paths, fields, and status codes |
| Auth tests | API key and JWT role behavior for protected operations |
| Data consistency | Cache artifact correctness against canonical core tables |
| Failure tests | Postgres restart/crash with cache artifact loss and successful rebuild |
| Load tests | p95 latency targets on high-traffic read endpoints |
| Upload tests | Replay upload size handling and retrieval integrity |
| Versioning tests | `v2` stability while `v3` evolves independently |

Release gates:
- No unresolved `P0` or `P1` compatibility mismatches for in-scope `v2` endpoints.
- All acceptance suites pass in CI.
- Observability dashboards and SLO alerts are configured before cutover.

## 13. Risks and Mitigations

Risk:
- `UNLOGGED` cache tables can lose data on crash/restart.
Mitigation:
- Deterministic rebuild jobs, startup warmup gates, and health-state signaling.

Risk:
- Strict `v2` compatibility can constrain data model improvements.
Mitigation:
- Isolate improvements to `v3` and enforce mandatory `v2` contract test suites.

Risk:
- PostgreSQL-only strategy can concentrate load on one system.
Mitigation:
- Index/caching discipline, materialized views, workload profiling, and capacity planning.

## 14. Success Metrics

- `v2` compatibility pass rate: `100%` for all in-scope public endpoints.
- Time-to-first-stable release compared with baseline planning targets.
- Dependency reduction: zero Redis requirement in production architecture.
- Adoption of `v3` by first-party frontend clients.
- Improvement in p95 latency for primary user-facing leaderboard and profile reads.

## Public Interfaces and Types to Explicitly Add

- API versioning policy:
  - `v2` compatibility.
  - `v3` innovation.
- Canonical identifier serialization rule for 64-bit fields.
- Cache object types in `cache` schema:
  - `cache.jumpstat_top30`
  - `cache.record_recent_top`
  - `cache.rank_distribution`
  - `cache.search_result`
- Worker interface contracts:
  - refresh cadence
  - invalidation triggers
  - rebuild idempotency rules

## Assumptions and Defaults (Locked)

- Backend framework remains FastAPI with typed models and OpenAPI generation.
- PostgreSQL is the only persistent and cache backing service.
- Phase 1 excludes admin parity and focuses on public API parity.
- `v2` remains stable and strict; richer data is introduced in `v3`.
- PRD file path: [info/gokz-top-v2-prd.md](/Users/cinyan10/Code/kzcharm/gokz-top-v2/info/gokz-top-v2-prd.md).
