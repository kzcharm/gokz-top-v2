# Players APIs + Admin Route Split (`/admin/users`, `/admin/players`)

## Summary
Implement the new players backend endpoints and split admin UI routes so:
1. Current users-admin page moves to `/admin/users`.
2. `/admin` redirects to `/admin/users` for backward compatibility.
3. New `/admin/players` displays all player-table rows.
4. Read players endpoints are public; write players endpoints require authentication.
5. Use `offset`/`limit` query params (query model) for player listing.
6. Add a reusable global `PlayerDisplay` showing country flag + rounded avatar + alias/name.
7. Add required table comments:
`Users`: “Website users for this project”
`Players`: “all Steam Players (who has played or potentially will play kz ( some mapper doesn't even played once, but we need to ensure them here)”

## API / Interface Changes

### Backend endpoints
1. `GET /v1/players/` (public)
Uses query model (`offset`, `limit`) via FastAPI query-param model pattern.
Returns `PlayersPublic` with `data` and `count`.

2. `POST /v1/players/` (public)
Batch read by Steam IDs.
Request: `steamid64s: list[str]`.
Response preserves request order with null placeholders for missing players:
`data: list[PlayerPublic | None]`, plus `count`.

3. `PUT /v1/players/{steamid64}/steam` (authenticated)
Upsert one player from Steam API.
Returns `PlayerPublic`.

4. `PUT /v1/players/{steamid64}` (authenticated)
Update editable player profile fields (for now: `alias`, `country`).
Returns `PlayerPublic`.

### Frontend routes
1. `/admin` becomes redirect-only route to `/admin/users`.
2. `/admin/users` contains existing users admin table.
3. `/admin/players` contains players table (read-focused page for now).

## Backend Implementation Plan

1. Add players router file [players.py](/Users/cinyan10/Code/kzcharm/gokz-top-v2/backend/app/api/routes/players.py) with the 4 endpoints and auth split:
Read endpoints: no `CurrentUser` dependency.
Write endpoints: `CurrentUser` dependency.

2. Add request/response/query models in [player.py](/Users/cinyan10/Code/kzcharm/gokz-top-v2/backend/app/models/player.py):
`PlayersListQuery` (`offset`, `limit`), `PlayerUpdate`, batch request/response models with nullable entries.

3. Extend CRUD in [player.py](/Users/cinyan10/Code/kzcharm/gokz-top-v2/backend/app/crud/player.py):
Add list-with-count by `offset/limit`, batch fetch preserving input order, update alias/country, and `Player -> PlayerPublic` mapper.

4. Register router in [main.py](/Users/cinyan10/Code/kzcharm/gokz-top-v2/backend/app/api/main.py).

5. Export new symbols in [__init__.py](/Users/cinyan10/Code/kzcharm/gokz-top-v2/backend/app/crud/__init__.py) and [__init__.py](/Users/cinyan10/Code/kzcharm/gokz-top-v2/backend/app/models/__init__.py).

## Frontend Implementation Plan

1. Add `country-flag-icons` dependency in [package.json](/Users/cinyan10/Code/kzcharm/gokz-top-v2/frontend/package.json).

2. Create reusable global component [PlayerDisplay.tsx](/Users/cinyan10/Code/kzcharm/gokz-top-v2/frontend/src/components/Common/PlayerDisplay.tsx):
Shows flag, rounded avatar, and display name (`alias || name || steamid64`).
Flag hover tooltip shows full country name.

3. Route split:
Update [admin.tsx](/Users/cinyan10/Code/kzcharm/gokz-top-v2/frontend/src/routes/_layout/admin.tsx) to redirect `/admin -> /admin/users`.
Add [admin.users.tsx](/Users/cinyan10/Code/kzcharm/gokz-top-v2/frontend/src/routes/_layout/admin.users.tsx) with existing users table and required Users comment.
Add [admin.players.tsx](/Users/cinyan10/Code/kzcharm/gokz-top-v2/frontend/src/routes/_layout/admin.players.tsx) with required Players comment and players table.

4. Update sidebar navigation in [AppSidebar.tsx](/Users/cinyan10/Code/kzcharm/gokz-top-v2/frontend/src/components/Sidebar/AppSidebar.tsx):
Admin entry points to `/admin/users`.
Add players-admin navigation entry for `/admin/players` (superuser only).

5. Update users table display in [columns.tsx](/Users/cinyan10/Code/kzcharm/gokz-top-v2/frontend/src/components/Admin/columns.tsx) to use `PlayerDisplay` for consistency.

6. Add players table components under `frontend/src/components/AdminPlayers/` (read-only in this scope; no edit/sync UI yet).

7. Regenerate OpenAPI client using [generate-client.sh](/Users/cinyan10/Code/kzcharm/gokz-top-v2/scripts/generate-client.sh) so `PlayersService` is available.

## Tests and Validation

1. Backend tests in new [test_players.py](/Users/cinyan10/Code/kzcharm/gokz-top-v2/backend/tests/api/routes/test_players.py):
Public `GET /players` works with `offset/limit`.
Public `POST /players` returns ordered nullable placeholders.
Unauthenticated `PUT /players/{steamid64}` and `PUT /players/{steamid64}/steam` are rejected.
Authenticated write endpoints succeed and persist data.

2. Extend direct-route branch tests in [test_async_runtime_branches.py](/Users/cinyan10/Code/kzcharm/gokz-top-v2/backend/tests/api/routes/test_async_runtime_branches.py) for new players routes.

3. Frontend Playwright coverage in [admin.spec.ts](/Users/cinyan10/Code/kzcharm/gokz-top-v2/frontend/tests/admin.spec.ts):
`/admin` redirects to `/admin/users`.
Superuser can access `/admin/users` and `/admin/players`.
Non-superuser is blocked from both admin routes.
Required comments are visible on both pages.
`PlayerDisplay` renders alias/name fallback + avatar + flag tooltip behavior.

## Assumptions / Defaults
1. “Any user can read players” means read endpoints are fully public (no login required).
2. “Only authenticated can update profile” applies to both write endpoints for now.
3. Player update actions in frontend are intentionally deferred; current frontend scope is read/list + display only.
4. Existing `/users` API keeps current `skip/limit`; only new players listing uses `offset/limit` as requested.
