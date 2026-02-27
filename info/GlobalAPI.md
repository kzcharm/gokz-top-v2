# GlobalRecordAPI rewrite summary

## High-level overview
- Solution layout: ASP.NET Core API (`GlobalRecordAPI.PublicAPI`) with Business/Repository/Models/Interfaces projects; Dapper + MySQL data access; Hangfire background jobs; Redis cache; Replay conversion library; Python points job.
- Domain focus: KZTimer/GOKZ global records, maps, servers, players, bans, jumpstats, replays, record filters, rankings/points, and admin tooling.
- Auth: API key (`X-ApiKey`) for server-to-server actions; JWT bearer for portal/admin; role-gated admin endpoints (GlobalAdmin/MapAdmin).
- Infra: MySQL, Redis (cache + rate limiting), Hangfire (jobs), NLog, Swagger, API versioning.

## Public API endpoints (V1 + V2)
Base path: `api/v{version}/...` with API versions 1.0 and 2.0 (default is 2.0). V1 and V2 are mostly identical; notable V2-only additions are called out below.

### Auth
- `GET /auth/status` -> auth status for API key or JWT
- `GET /auth/jwt/status` -> JWT status (requires GlobalAdmin)

### Records
- `GET /records/place/{id}` -> place for record id
- `GET /records/{id}` -> record by id (V2 only)
- `GET /records/top/` -> top records by filters
- `GET /records/top/world_records` -> world record counts by filters
- `GET /records/top/recent/` -> recent top records by filters
- `POST /records` -> submit record (requires Server role, API key)
- `GET /records/record_filter/` -> stubbed (returns placeholder)

### Replays (under Records)
- `POST /records/{record_id}/replay` -> upload replay blob (V2 has 100MB limit attribute)
- `GET /records/{record_id}/replay` -> replay by record id
- `GET /records/replay/{replay_id}` -> replay by replay id
- `GET /records/replay/list` -> list records that have replays

### Record filters + rankings
- `GET /record_filters` -> record filters by parameters
- `GET /record_filters/distributions/` -> rank distributions by record filter
- `GET /player_ranks` -> player rank aggregates (points, rating, finishes)

### Bans
- `GET /bans` -> ban list (filterable)
- `POST /bans` -> create ban (requires Server role, API key)

### Jumpstats
- `GET /jumpstats` -> jumpstats by filter
- `GET /jumpstats/{jump_type}/top` -> top jumpstats by filter
- `GET /jumpstats/{jump_type}/top30` -> cached top 30 per jump type
- `POST /jumpstats` -> submit jumpstat (requires Server role, API key)

### Players
- `GET /players` -> players by filter
- `GET /players/steamid/{steamid}` -> by SteamID
- `GET /players/steamid/{steamid}/ip/{ip}` -> by SteamID+IP (Server role)
- `GET /players/steamid/{steamid}/alts` -> alts (Steam auth + Admin role)
- `GET /players/get_banned_players/steamid?steamids=...` -> banned players by SteamIDs

### Maps, Modes, Servers
- `GET /maps` -> maps by filter
- `GET /maps/{id}` -> map by id
- `GET /maps/name/{map_name}` -> map by name

- `GET /modes` -> modes
- `GET /modes/name/{mode_name}` -> mode by name
- `GET /modes/id/{id}` -> mode by id

- `GET /servers` -> servers by filter
- `GET /servers/{id}` -> server by id
- `GET /servers/name/{server_name}` -> server by name
- `POST /servers/apply` -> apply for server (JWT)
- `GET /servers/owned` -> servers owned by current JWT user

## Admin API endpoints (V2 only)
Base path: `api/v{version}/admin/...` (JWT required; roles noted).

- **Bans** (GlobalAdmin)
  - `GET /admin/bans`
  - `POST /admin/bans` (create)
  - `PUT /admin/bans/{id}` (update)

- **Records** (GlobalAdmin)
  - `POST /admin/records/delete`

- **Jumpstats** (GlobalAdmin)
  - `POST /admin/jumpstats/delete`

- **Record filters** (GlobalAdmin or MapAdmin)
  - `POST /admin/record_filters` (bulk create)
  - `POST /admin/record_filters/delete` (bulk delete)

- **Servers** (GlobalAdmin)
  - `GET /admin/servers`
  - `PUT /admin/servers/{id}`
  - `POST /admin/servers/approve/{id}`
  - `POST /admin/servers/reject/{id}`
  - `POST /admin/servers/{id}/newkey`

- **Maps** (GlobalAdmin or MapAdmin)
  - `POST /admin/maps`
  - `PUT /admin/maps/{id}`
  - `DELETE /admin/maps/{id}`

- **Modes** (GlobalAdmin)
  - `PUT /admin/modes/{id}`

## Database schema (globalrecordapi)
NOTE: there are multiple schema scripts; migrations and repository code imply the "record_filter_id" schema is current. `Database/Schema.sql` contains older variants with `record.map_id`, `record.mode`, and `record_filter.mode` (string). See "Schema drift" below.

### Core tables
- **record** (current, per migrations and repository usage)
  - `id` int PK AI
  - `steamid64` bigint
  - `server_id` int
  - `record_filter_id` int (FK -> record_filter.id)
  - `time` decimal(12,3)
  - `teleports` int
  - `created_on` datetime
  - `updated_on` datetime
  - `updated_by_id` bigint

- **record_deleted** (used by repository; schema implied by insert)
  - `id` int
  - `steamid64` bigint
  - `server_id` int
  - `record_filter_id` int
  - `time` decimal(12,3)
  - `teleports` int
  - `created_on` datetime
  - `updated_on` datetime
  - `updated_by_id` bigint
  - `delete_reason` int

- **record_filter**
  - `id` int PK AI
  - `map_id` int (FK -> map.id)
  - `stage` int
  - `mode_id` int (FK -> mode.id)
  - `tickrate` int
  - `has_teleports` tinyint(1)
  - `created_on` datetime
  - `updated_on` datetime
  - `updated_by_id` bigint

- **record_top**
  - `record_id` int (FK -> record.id)
  - `record_filter_id` int (FK -> record_filter.id)
  - `points` int
  - PK (`record_id`,`record_filter_id`)

- **record_recent_top**
  - `id` int PK AI
  - `record_id` int
  - `place` int
  - `top_100` int
  - `top_100_overall` int
  - `created_on` datetime

- **rank_distribution_record_filter**
  - `record_filter_id` int PK
  - `c` double
  - `d` double
  - `loc` double
  - `scale` double
  - `top_scale` double
  - `created_on` datetime
  - `updated_on` datetime
  - `updated_by_id` bigint

### Reference tables
- **map**
  - `id` int PK AI
  - `name` varchar(255)
  - `filesize` int
  - `validated` boolean
  - `difficulty` int
  - `created_on` datetime
  - `updated_on` datetime
  - `approved_by_steamid64` bigint

- **server**
  - `id` int PK AI
  - `api_key` varchar(36)
  - `name` varchar(255)
  - `ip` varchar(255)
  - `port` int (default 27015)
  - `owner_steamid64` bigint
  - `approval_status` int
  - `approved_by_steamid64` bigint
  - `created_on` datetime
  - `updated_on` datetime

- **mode**
  - `id` bigint PK AI
  - `name` varchar(255)
  - `description` varchar(1023)
  - `latest_version_description` varchar(255)
  - `latest_version` int
  - `website` varchar(255)
  - `repo` varchar(255)
  - `contact_steamid64` bigint
  - `updated_by_id` bigint
  - `created_on` datetime
  - `updated_on` datetime

- **player**
  - `id` int PK AI
  - `steamid64` bigint UNIQUE
  - `last_seen` datetime
  - `name` varchar(128)

- **player_log**
  - `id` bigint PK AI
  - `server_id` int
  - `steamid64` bigint
  - `ip` varchar(255)
  - `created_on` datetime
  - index `player_log_search` (`steamid64`,`ip`)

### Bans
- **ban**
  - `id` int PK AI
  - `ban_type` varchar(45)
  - `expires_on` datetime
  - `ip` varchar(45)
  - `steamid64` bigint
  - `notes` varchar(1024)
  - `stats` varchar(512)
  - `server_id` int
  - `updated_by_id` int
  - `created_on` datetime
  - `updated_on` datetime

- **ban_deleted**
  - same as `ban` plus `delete_reason` int

### Jumpstats
- **jumpstat**
  - `id` int PK AI
  - `server_id` int
  - `steamid64` bigint
  - `jump_type` int
  - `distance` float(7,4)
  - `jumpstat_data_id` int
  - `tickrate` int
  - `msl_count` int
  - `strafe_count` int
  - `is_crouch_bind` int
  - `is_forward_bind` int
  - `is_crouch_boost` int
  - `updated_by_id` int
  - `created_on` datetime
  - `updated_on` datetime
  - index `jumpstat_top` (`steamid64`,`jump_type`,`distance`,`tickrate`)

- **jumpstat_data**
  - `id` int PK AI
  - `json_jump_info` varchar(32768)
  - `updated_by_id` int
  - `created_on` datetime
  - `updated_on` datetime

- **jumpstat_deleted**
  - same as `jumpstat` plus `delete_reason` int

### Other
- **replay**
  - `id` int PK AI
  - `record_id` int (FK -> record.id)
  - `replay_data` LONGBLOB

- **steam_user**
  - `steamid64` bigint PK
  - `communityvisibilitystate` int
  - `profilestate` int
  - `personaname` varchar(256)
  - `lastlogoff` int
  - `commentpermission` int
  - `profileurl` varchar(256)
  - `avatar` varchar(256)
  - `avatarmedium` varchar(256)
  - `avatarfull` varchar(256)
  - `personastate` int
  - `primaryclanid` varchar(256)
  - `timecreated` int
  - `personastateflags` int
  - `loccountrycode` varchar(256)
  - `created_on` datetime
  - `updated_on` datetime
  - `updated_by_id` bigint

- **search_result**
  - `id` bigint PK AI
  - `search` varchar(512)
  - `result` varchar(512)
  - `created_by` bigint
  - `created_on` datetime

### Views
- `jumpstat_view` -> jumpstat + computed Steam2 ID + jump_type_string
- `all_records` -> union of external `player128/102/64_*` tables in `kztimerdb`

## Identity database (globalrecordapi_identity)
ASP.NET Identity tables (standard schema):
- `AspNetUsers`, `AspNetRoles`, `AspNetUserRoles`, `AspNetUserClaims`, `AspNetRoleClaims`, `AspNetUserLogins`, `AspNetUserTokens`.

## Background jobs and batch processing
- Hangfire jobs (queues `api`, `Default`, `portal`):
  - `UpdateCacheJob` -> refresh jumpstats top30 cache; refresh record_recent_top cache.
  - `ConvertReplayJob` -> convert replays to GOKZ format (plugin id 201).
  - `SearchJob` -> alt account lookup; stores results in `search_result`.
  - `SyncWithExternalDBJob` -> sync servers/maps/bans/records from external DB.
  - `PlayerNameJob` -> refresh Steam user info.
- PointsJob (Python): `PointsJob/RefreshDistributionsAndPoints.py` computes Burr distribution fit for each record_filter and updates `rank_distribution_record_filter` + `record_top.points`.

## Notable implementation details
- API key auth populates `HttpContext.Items["server"]` and sets role `Server` (approval_status > 0 required).
- JWT auth used for portal/admin; roles include `GlobalAdmin` and `MapAdmin`.
- Rate limiting uses Redis: 500 req / 5 min and max 5 concurrent requests for unauthenticated IPs.
- Long-to-string JSON converter on most controllers to avoid JS precision loss for 64-bit IDs.
- Binary input formatter accepts `application/octet-stream` for replay uploads.

## Schema drift / tech debt to watch during rewrite
- `Database/Schema.sql` defines `record` with `map_id`, `stage`, `mode` (string), `tickrate` and `record_filter` with `mode` (string). Code and migrations use `record_filter_id` (normalized) and `record_filter.mode_id` (FK to `mode`).
- `record_deleted` schema in `Schema.sql` does not match repository inserts (which include `record_filter_id`), suggesting an outdated or divergent table definition.
- `record_recent_top_deleted` is used by repository but not defined in core schema scripts.
- Jumpstat JSON field moved to `jumpstat_data`, but model still exposes `json_jump_info` (legacy field).
- `RecordsController.GetRecordFilterByParameters` currently returns a placeholder (`new Place()`), not real data.

## Suggested starting points for rewrite
- Normalize schema scripts to match repository/model usage (record_filter_id + mode_id) before porting.
- Decide canonical source of truth for points/rank distributions (Hangfire vs PointsJob) and consolidate.
- Consider moving record/replay pipelines to a dedicated service boundary (upload, validation, conversion).
- Formalize API contracts (OpenAPI from Swagger) and deprecate V1 if possible.
