# GoKZ Top - Project Features

This document summarizes the core features implemented in this repository (backend + frontend), focused on the current product behavior rather than template defaults.

## Core Product Features

### 1. KZ records and ranking platform
- Tracks player records across KZ modes (`KZT`, `SKZ`, `VNL`, `NKZ`).
- Supports map-level run distinctions (overall/TP/pro where applicable).
- Stores and serves world-record cache data for map pages and profile views.
- Includes a rating and points system with mode-aware logic and weighted calculations.
- Provides both classic and newer points/rating fields for leaderboard use.

### 2. Leaderboards and competitive views
- Global leaderboards per mode with multiple sort options (rating, points, WR counts, tier completions, etc.).
- Fire Power leaderboard for previous complete periods (`day`, `week`, `month`, `year`).
- Country and region filtering on leaderboard queries.
- Friends-only leaderboard filtering when viewer identity is provided.
- Per-player rank lookup support in leaderboard responses.

### 3. Maps discovery and review system
- Map list and detail pages with filtering (name, validation status, difficulty, author info, timestamps).
- Map metadata support including workshop IDs/URLs and author attribution.
- Map reviews and review summary endpoints.
- Player map comments/ratings retrieval.
- Map sync endpoint for pulling map updates from external/global data.

### 4. Player profiles and social features
- Player profile pages with progress/records context.
- Player search and batch player retrieval.
- Friends data integration and manual/background friend sync support.
- Player likes system (like counts, likers, admin overviews).
- Player social links (self-service plus admin management).
- Player recap/statistics endpoints with caching and force refresh controls.
- Playtime-by-server-group analytics endpoint for individual players.

### 5. Public servers and live status
- Public server registry with CRUD operations.
- Ownership-aware permissions (superuser/global roles/server owner behavior).
- Server group support and server-group-based views.
- Status ingestion endpoint for servers (push updates via authenticated user/API key).
- Cached server status retrieval endpoints (global or by group).
- Frontend server browser with filter controls and navigation to server detail pages.

### 6. Live stream aggregation
- Live page that aggregates streamer status for linked players.
- Twitch and Bilibili live checks via backend integrations.
- Thumbnail proxy endpoint for external image/CORS handling.
- Live indicators integrated into navigation for discovery.

### 7. Authentication, users, roles, and settings
- Steam OpenID login flow with callback verification.
- JWT authentication for user sessions.
- API key support (including reveal/delete flows) for service-to-service usage.
- Role model with role assignment endpoints.
- User profile/settings updates, default mode/page preferences, and account controls.
- QQ binding code generation flow for third-party linkage use cases.

### 8. Admin and operations features
- Admin UI sections for users, public servers, map reviews, VNL tiers, likes, sessions, social links, and settings.
- GlobalAPI admin section for bans/maps/modes/players/records/record-filters management workflows.
- Dedicated sync status controls for long-running integrations (records/bans/player profile, etc.).
- Record-filter management and statistics endpoints.

### 9. Search and utility services
- Unified search endpoints for players, servers, and maps.
- IP geolocation utilities (single and bulk lookup).
- Purity stats endpoint for player activity concentration on server groups.
- Health-check and rating-formula utility endpoints.

### 10. Analytics and recap experiences
- Public stats endpoints for:
  - daily active players
  - daily/monthly active users
  - website user totals
  - popular server groups by period
- Player-level recap and stats APIs with caching.
- Frontend dashboard and recap pages with chart-driven analytics and archive-style yearly summaries.

## Platform and Engineering Features

### Backend
- FastAPI application with modular route structure.
- SQLModel + PostgreSQL persistence layer.
- Alembic migrations for schema evolution.
- Background workers started at app lifespan:
  - server status worker
  - global bans sync worker
  - global records sync worker
  - player profile sync worker
  - daily active player worker
  - popular server groups worker
  - active user worker
  - fire power leaderboard worker
  - map distribution worker
- OpenAPI schema generation with tagged endpoints.

### Frontend
- React + TypeScript app using TanStack Router and TanStack Query.
- Chakra UI component system.
- Multi-language support via i18next (locale bundles present for `en`, `de`, `ru`, `zh`).
- Route-driven app structure with desktop/mobile navigation variants.
- Generated API client integration.

### Testing and delivery
- Backend tests with Pytest.
- Frontend E2E test setup with Playwright.
- Docker Compose-based local/prod workflows and deployment scripts/docs.

