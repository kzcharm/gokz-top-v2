# Product Requirements Document - GOKZ.TOP v2

- Status: Draft
- Owner: gokz-top-v2 team
- Last Updated: 2026-10-24
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
- Profile skill radar uses six scope-aware raw ratings calculated from virtual entries at each analyzed main map's unchanged best NUB/PRO PB points. Each skill independently orders its map evidence by PB points with deterministic map-ID tie-breaking and retains at most `50 / 6` full-portion entries, representing the per-skill share expected from 50 evenly distributed six-skill maps. A map portion `w` provides `100 * w` atomic entries, including fractional entries, and a final block that crosses the limit is truncated continuously. Each skill uses an independently configurable full-portion decay without changing the overall rating formula. Separate per-skill, per-scope percentile curves calibrate levels 2–10 manually; a unique population leader anchors at `10.99999`, tied leaders anchor at `10.99`, and both display as `10.99` under the site-wide two-decimal floor rule. The radar currently provides a relative plot that keeps the strongest skill at the same radius as the global 0–11 calculation, then expands the player's minimum-to-maximum range inside that footprint. Its inner bound rises with the weakest absolute global rating, preventing a near-11 skill from looking genuinely weak. Every axis label contains the globally calibrated rating. The direct Global view is not currently exposed, though its plot calculation is retained for possible future use. Skill ratings are shown only when available, and the existing overall rating converter is unchanged. Production rollout requires an explicit raw rebuild and fresh six-skill converter calibration for `OVR`, `KZT`, `SKZ`, and `VNL` after deployment.
- `/compare` accepts two player identifiers and exposes a shareable scope-aware comparison of rating, points, global rank, tiered validated-main-map completion, and NUB/PRO main-stage PBs. The route supports replacing either player through search, swapping the sides, and filtering each PB table to maps finished by both players. A NUB/PRO toggle selects one profile-style completion chart with tier-colored, 20px bars growing outward from the center for the two players. Large avatars appear once; player hover/focus highlights completion bars, skill radar, and metrics. Both WR fields hide when all four WR counts are zero. A shared 0–11 skill radar accompanies compact summary metrics. Runs support map/tier filters, player-targeted mode/server/time/points/teleport/date filters, column sorting (defaulting to Player 1’s latest PB finish), both players’ points and preference-formatted finish dates, and persisted rows-per-page pagination. SteamID64 URL parameters remain exact strings without quotes. Authenticated player context menus prefill the viewer against the selected player.
- Public player leaderboard is now available at `/v1/leaderboards/players` with scope switching, server-side sorting, pagination, and eligibility-based membership semantics. Its selectable skill column can display and sort by any of the six independently calibrated skills.
- Public maps leaderboard is now available inside the `/leaderboards` page `Maps` tab, backed by `/v1/leaderboards/maps`, with scope switching, full validated-map reads, and client-side sorting/filtering for record-derived map metrics plus review summary fields.
- Public community leaderboard entries expose the player's largest cached verified platform follower audience across Bilibili, YouTube, and Twitch, including the platform URL for the displayed icon link and server-side sorting by that follower count.
- Public country leaderboard is available at `/leaderboards/countries`, backed by `/v1/leaderboards/countries`; it ranks countries with at least 10 eligible players by top-10 average rating and shows the country median rating, ranked and 30-day active-player counts, and the top three players.
- Global and filtered leaderboards (scope, geography, and period when applicable).
- Rank lookup support for profile and map contexts.
  - Profile Runs can display and sort live PB ranks through a Show ranks setting, disabled by default and remembered per browser. Rank calculations are requested only while enabled and only for the visible page, with at most 50 records per request. Ranked views use pagination instead of automatic loading, and rank sorting applies within the current page. Active bans are excluded from competitive ranks, and visible ineligible PBs show a dash. This does not change points or rating refresh schedules.
- Daily rank maintenance runs as one midnight-UTC pipeline over the previous UTC day's changed `record_pb` rows, rebuilding touched PB point buckets first, then touched leaderboard rows, then touched maps leaderboard rows selected from `Record.updated_at`, then touched Steam-backed player profiles, then attempting KZ-only friends sync for those same players.
- Player leaderboard rebuilds persist each contributing PB row's raw rating contribution on `record_pb`, and player profile record lists expose it as a `Rating` column beside points.
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
- `/dashboard` defaults to `/dashboard/wrs`, where the newest main-course WR events per scope appear as responsive cards with map and tier filters, a NUB/PRO view toggle, and the app-wide scope filter. Initial population uses current 1000-point PB winners, while newly established WRs append to the uncapped cache without removing the WRs they supersede. The run time and active view's improvement plus previous holder appear over the map image. A zero-teleport run retains its combined NUB and PRO achievements in either view, including its positive improvement over the previous eligible WR or a First WR label.
- The recent-WR dashboard loads 20 cards initially and automatically loads additional 20-card batches while scrolling until its frontend-only 100-card cap is reached; the database does not prune eligible WR events. Filtered WebSocket snapshots refresh the first batch; when a new WR changes the head of the feed, loaded later batches are discarded and can be fetched again so offset pages never overlap. The API stays in a preparation state until the standalone resumable cache backfill has completed; Alembic performs schema creation only.
- World-record and recent-record experiences.
- Scope-dependent points for rank-oriented queries.
- Selected leaderboard and record list surfaces exclude players with any active mirrored ban by default, while recent feeds and record detail views remain unchanged. Local admin-created bans are visible in `/v1/bans` but do not participate in the mirrored-ban compatibility flows unless they also have an upstream GlobalAPI id.

### 5.3 Maps and Reviews
- Map catalog and detail pages with filters and metadata.
- Map catalog cards display manually imported backend skill-analysis fractions, use 100% Unknown when analysis is unavailable, and support sorting by each measured skill. Ordered analysis segments remain stored for future features but are excluded from normal map responses.
- Validated maps can expose a BSP `download_url` once the production map file distributor has uploaded the raw BSP to Cloudflare R2.
- Production map file distribution maintains raw BSP files, optional FastDL-sized BZ2 archives for BSPs under 150 MB, a full `packages/GlobalMaps.7z`, and per-date release ZIPs for maps updated on a given UTC date.
- Deleted Workshop maps can be preserved only when operators seed their BSPs manually from the starter `GlobalMaps.7z`; otherwise the distributor records the missing file and continues syncing Workshop-available maps.
- Map review/rating flows.
- v1 map and course tiers are course-scoped rather than TP/PRO-scoped: each exact course has one tier per mode, `record_filter` rows only determine availability, and tier reads normalize to integer `0..8` values where `0` also covers unavailable/unknown/impossible cases.
- Authenticated players can author website reviews only after earning a main-stage OVR PB on the map.
- Map review authoring must prefill from the player's latest review on that map, while normal website saves continue to target the website review row only.
- Players can delete all of their review comments for a map without deleting any rating rows; this applies across website and server-group review rows.
- Tight linkage between map pages and relevant record context.

### 5.4 Player Profile Experience
- Rich profile overview (identity, ranking highlights, competitive summary).
- Player profiles show tournament achievement badges below their rating/points/rank summary. Root admins manage v2-native S/A/B/C tournaments and award placements one through four, with gold, silver, and bronze trophies for first, second, and third/fourth respectively.
- Profile and shared player-display reads must refresh missing or seven-day-stale Steam identity data in the background, then update visible names, avatars, countries, and Steam custom IDs immediately when the refresh completes.
- SourceMod servers can run `gokz-top-profile` for in-game profile menus, rank/chat/clan tags, rating lookups, and scoreboard level icons backed by `/v1/leaderboards/players/{identifier}` while preserving the legacy `gokz-profile` native compatibility surface.
- Player profiles show linked X, Bilibili, YouTube, GitHub, and Twitch accounts from v2-native social-link records, with unverified links visible but marked.
- Verified Bilibili, YouTube, and Twitch social links can contribute lazily cached follower counts to community-facing leaderboard context, while unverified links are ignored for follower display.
- Player profiles now expose a dedicated Friends tab at `/profile/{identifier}/friends`, showing only mutual website-known KZ players from the target player's Steam friends list.
- Owners should auto-attempt one friends sync the first time they open their Friends tab if no earlier `friends_sync` action has been recorded, while still retaining a manual Sync button for later refreshes.
- Friends-tab reads must show a public privacy warning when the player's Steam profile or Steam friends list is private, because that Steam visibility state is itself public.
- Player profiles expose comments at the bottom of the Home tab, where authenticated users can leave short public comments for another player.
- Player-comment writes must trim whitespace, reject blank input, and enforce a bounded text length; both the comment author and the target profile owner can delete a posted comment.
- Authenticated players have a notifications inbox at `/notifications`, surfaced by a navbar bell with an unread badge. The first notification set covers profile likes, profile comments, new followers, and future-only KZT/SKZ/VNL NUB/PRO WR-beaten events. Notifications remain unread until the player opens/clicks a notification or uses the mark-all-read action.
- Authenticated players can submit in-app player reports from player context menus and record row context menus; record-originated reports include the record UUID as context, require a description, warn against joke/abusive reports, and notify all admins plus the configured root user.
- Map-top admin mode provides a right-click action to soft-invalidate all strictly faster historical runs for all players within the same map/course, mode scope, and NUB/PRO category. Country/region filters and pagination do not restrict it. The confirmation previews affected runs in collapsed player groups using `PlayerDisplay`, with counts and time ranges; expanding shows individual runs. Preview failures or empty results block deletion, and changed records require renewed confirmation. Admin deletion invalidates raw runs and removes referencing PB entries without waiting for fallback PBs, points, WRs, or cache rebuilds. Admin invalidations notify each reporter once per exact reported record; sync/import/backfill invalidations do not notify.
- `/live` lists player-centric verified stream cards sourced from verified Bilibili and Twitch links, with filters for live versus previously streamed players.
- `/media` lists only positively classified KZ-related uploads from verified YouTube and Bilibili links. Exact `KZ`, `GOKZ`, `Kreedz`, and `CS2KZ` tags, standalone title/description keywords, and standalone `kz_`, `bkz_`, `kzpro_`, or `xc_` map-shaped tokens qualify; map tokens do not need to exist in the local catalog. Rejected and unresolved uploads remain internal for the 90-day retention window, and temporary metadata failures must not hide an already-positive upload. Bilibili ingestion must use signed creator-upload polling with an optional server-only dedicated-account session cookie so anti-bot responses do not prevent the public feed from updating.
- Offline `/live` cards must show the most recently observed stream across a player's enabled platforms, so future multi-platform support can prefer the newest Twitch/YouTube/Bilibili activity rather than a fixed platform order.
- When Cloudflare R2 is configured, `/live` stores each changed Bilibili and Twitch stream keyframe at a new immutable UUIDv7 URL, skips uploads when the image hash is unchanged, and uses the last saved image for offline stream cards. Superseded objects are removed after the replacement is committed, while an hourly sweep removes unreferenced keyframes older than 24 hours.
- Historical performance slices (records, jumpstats, replays, trend-oriented data).
- Profile views now consume a consolidated player stats endpoint backed by lazily refreshed PostgreSQL cache rows, with UTC daily activity, total playtime, most-played-server breakdowns, and most-played-map breakdowns by records submitted and record time available on the profile.
- An authenticated player's own `/profile/:identifier/runs` page must subscribe to player-filtered live record events and refresh its PB data automatically when new records become available; anonymous visitors and viewers of other players' runs must not open that subscription. WR times are blue when the winning run has zero teleports and yellow when it has teleports, including zero-teleport winners shown in the NUB bucket. The Show WR time and Show WR gap choices persist in first-party browser cookies.
- Player profile sidebars expose a `Fav Server` row below Long Jump. By default it reflects the player's all-time most-played server/group from cached stats; grouped servers display the server group name and link to the server-group page.
- Shareable, fast-loading profile UI with clear information hierarchy.

### 5.5 Servers and Live Status

- Server cards, tables, and details show **Connect via Steam** only for reported standalone CS:GO App ID `4465480`. Servers reporting `730`, any other ID, or an unknown ID retain only **Copy server address**, which copies the console `connect IP:port` command. Existing unknown IDs populate through background A2S queries.
- Public server registry and ownership-aware management.
- Server visibility is controlled independently from operational status. Hidden servers continue normal heartbeat and health collection but must not appear in public lists, detail/history reads, server-group counts, or live WebSocket updates.
- Admin server management provides Root Admin access to all GlobalAPI/public servers and Server Owner access to owned servers, with approval control reserved for Root Admins.
- Root Admins and Server Owners can select one or more accessible GlobalAPI servers and export valid VNL/SKZ/KZT records as a streamed, gzip-compressed MySQL script for an existing GOKZ LocalDB database.
- Backend operators can export valid VNL/SKZ/KZT/NKZ records for explicit GlobalAPI server IDs or complete server groups as a streamed `.csv.gz` archive, with optional inclusive UTC creation-time bounds, alias-aware player names, GOKZ-local mode/runtime values, long map names, and exclusion counts for invalid records and incompatible Steam IDs.
- Backend operators can export the distinct players represented by the same eligible server records as a `.csv.gz` archive, enriched with permanent-ban status and the newest IP, earliest connection, and latest completed-session disconnect from player sessions across all servers.
- Root Admins can investigate possible alternate accounts from player-session IP evidence using bounded exact-IP, `/24`, or `/16 + city` traversal; the workflow returns explainable links and skipped busy buckets, not scores or automated enforcement.
- Live status ingestion and display.
- Server group support and filterable browsing.
- Cached live status must be served from PostgreSQL-backed cache rows, not live upstream queries on page load.
- Server location coordinates must be stored with the server row and refreshed during server writes when location data is missing or the IP changes; online IP location APIs are preferred, with the local GeoIP database retained as fallback.
- Support richer plugin heartbeats keyed by server-group API keys, with A2S polling and Steam server-list discovery as collector-side inputs.
- Show a GlobalAPI status badge on each server map image when `gokz-global` reports valid API key, plugin, settings, and map checks plus at least one available KZT, SKZ, or VNL mode; expose the individual checks on hover and leave player validity explicitly unevaluated.
- The primary SourceMod live-status publisher is `gokz-top-servers`, which reuses `gokz-top-core` server-group auth config and caches its resolved public IPv4 locally before pushing `/v1/servers/status`.
- Plugin heartbeat player payloads must preserve richer run state than A2S can provide, including clan tag, movement mode, timer status, pause state, teleports, timer time, stage, and connection duration.
- Plugin heartbeats may additionally report each player's average round-trip ping plus net-graph-style server `SV` and `VAR` values in milliseconds; these fields remain optional for compatibility with older plugin versions and are shown only from the current authoritative snapshot.
- SourceMod plugins can submit player connection sessions via authenticated `/v1/player-sessions` connect, heartbeat, and disconnect events for playtime, activity, map-time, and shared-IP analytics.
- Open player sessions are closed automatically after heartbeat timeout using the last known heartbeat as the disconnect timestamp.
- Preserve last-known server identity fields when a server goes offline so players can still see which server is down.

### 5.6 Jumpstats and Replays
- Jumpstats submission/query/top views.
- Public `GET /v1/maps/lj-rooms?map_name=...` returns manually imported analyzer room/slot coordinates without authentication; an imported map with no detected room returns an empty room list, while absent data returns not found.
- GOKZ servers can run `gokz-top-ljroom` to fetch the current map's data at map start and provide `!lj [distance]`, nearest-distance fallback, and a private saved default distance while stopping any active timer before teleporting.
- Public jumpstat reads remain available through:
  - `/v1/jumpstats` for global list/top reads
  - `/v1/jumpstats/{id}` for single jumpstat detail
  - `/v1/jumpstats/{id}/visualization` for replay-derived route visualization payloads
  - `/v1/players/{identifier}/jumpstats` for per-player history
- SourceMod plugins can now submit jump replays through server-group-authenticated `POST /v1/jumpstats` multipart uploads; the backend derives the persisted jumpstat payload from the replay file instead of trusting separate client-reported stats.
- SourceMod plugins can pre-check jump replay retention eligibility with `GET /v1/jumpstats/replay-eligibility` and upload eligible raw replay files to `POST /v1/jumpstats/replay`.
- The SourceMod uploader supports both legacy paths and UUID filenames without recorder changes, derives identity from the replay even after disconnects, and persists snapshots and retry state. Shared SourceMod installations elect one upload worker and release ownership when that instance hibernates. Historical replay recovery is manual through existing endpoints and requires no app changes.
- Jump replay retention keeps each player's best 10 Long Jump replay files and best replay file for each other supported jump type in every mode; cleanup removes old replay files that fall outside those keep sets without deleting jumpstat rows.
- Jumpstat persistence is v2-native, keyed by UUIDv7 and server-group ownership rather than mirrored GlobalAPI server IDs.
- Per-strafe breakdown rows are stored inline in PostgreSQL JSONB on the parent jumpstat row; there is no separate strafe detail table.
- Replay-derived route visualizations are cached as versioned JSONB on the parent jumpstat row, rebuilt lazily from the stored replay when the cache is missing or stale, and surfaced on the public jumpstats leaderboard dialog.
- Replay-derived writes currently reconstruct headline jumpstat fields plus `deviation`, while `edge` remains unavailable because it still depends on map/world traces outside the replay file.
- Replay files are stored locally under a shared replay root with type-specific subdirectories, with jump replays under `jumps/<jumpstat-id>.replay` and run replays under `runs/<normalized-map-name>/<record-uuid>.replay`.
- Manual import tooling now supports historical run replay backfills from `.replay` files, directories, `.zip` archives, and `.7z` archives, matching exact player/mode/map/stage/time plus a 24-hour `created_at` window and rejecting ambiguous or non-`NRM` v2 replays.
- `/v1` record-shaped responses now expose `is_replay_available` so replay visibility is integrated into player and map workflows without changing `/v0` compatibility payloads.
- Run and jump replay playback opens the standalone replay viewer at `replays.gokz.top`, backed by the `replay-viewer/` submodule and host-mounted exported map resources.
- External websites can deep-link public HTTPS GOKZ replay files into the standalone viewer with the mutually exclusive `replay_url` query parameter. The browser downloads the replay directly with provider-supplied CORS permission; external map-resource hosts, authenticated URLs, and a backend replay proxy are not supported.

### 5.7 Auth, Roles, and Settings
- User auth/session flows and API key support.
- Role-based access for admin/operator capabilities.
- Player preferences/settings persistence.
- Root admins can move the Discord community link between the navbar and footer from `/admin/settings`; the current navbar placement is the default.
- Root admins can enable or disable the deployment-local GlobalAPI record importer from `/admin/settings`; the setting defaults to enabled for backward compatibility, persists in the central app settings store, and does not affect other GlobalAPI synchronization tasks.
- Application-wide settings are persisted as typed JSONB payloads in a central key/value store, while public reads expose only explicitly safe fields and never encrypted secret payloads.
- Authenticated players can self-edit `alias` and `custom_id` from `/settings`, with independent 30-day cooldowns and no cooldown consumption for no-op submissions.
- Authenticated players can manually set `country` from `/settings`; manual country changes disable later automatic GeoIP/Steam overwrites but do not block later manual country edits.
- Authenticated players can manually set a favorite server from their own all-time played server/group options or choose `None`; any manual favorite selection, including `None`, disables future favorite-server auto-updates.
- `name` remains read-only in settings because it is synced from Steam rather than edited locally.
- Authenticated players can generate a short-lived QQ binding code from `/settings/binding-code` and send `/bind <code>` to the QQ bot to prove Steam-account ownership; a superuser configures the shared bot-verification secret at `/admin/settings`, the website stays stateless for this flow, the code keeps the `KZTOP` prefix while using a compact fixed-length alphanumeric body, and the bot owns the final QQ binding state. The bot can use the same secret via `X-QQ-Bot-Key` for trusted player actions such as submitting map ratings on behalf of a bound Steam account.
- Authenticated players can manage their own social links from settings; Discord links require self-serve OAuth ownership verification (one Discord account per player, one verified player per Discord account, remove before replacing), Twitch and YouTube links support self-serve OAuth verification, Bilibili links support self-serve profile-code verification, and superusers can still view, add, edit, delete, and verify player social links from admin.
- Authenticated players can manage Discord webhooks from `/settings`; enabled webhooks currently receive all supported stream-start events for the player's verified Twitch and Bilibili links, and each webhook shows its last-used time based on successful test sends or real deliveries.

### 5.8 Community Polls
- Public `/polls` browsing supports active/archive filtering and sorting by creation time, last activity, or total voters.
- Each poll has a shareable `/polls/{poll-id}` route, and polls with a configured voting deadline show that end time in list and detail views.
- Polls contain a title, optional description, 2–26 ordered options with optional descriptions, optional end time, and configurable selection limits (`0` means unlimited). Options retain stable `A`–`Z` identifiers, while visible vote-sorted results show a separate numeric rank.
- Signed-in users can vote once per poll and may change their selections when enabled by the poll author; votes cannot be withdrawn.
- Total voter counts are public. Open-poll option results are visible only to voters; closed-poll results are visible to everyone. Visible option results are ordered by vote count, highest first.
- Root admins are the only users who can create, edit, close, reopen, or delete polls and inspect voter audits. Options lock after the first vote.

## 6) Compatibility Strategy (Mirror + Extend)

### 6.1 Mirror Rules
- Mirror authoritative entities from GlobalAPI where required (for example maps/records/filters/bans).
- Preserve compatibility-critical identifiers and field semantics.
- Track sync status/lag for reliability and troubleshooting.
- Mirrored `record_filter` rows are availability-only in v2-native logic; exact 128-tick non-wildcard tiers are backfilled once into local `map_course_tier`, after which non-VNL tiers are admin-managed and VNL tiers continue syncing from the vanilla tier sheet.
- GlobalAPI bans are mirrored as append/update-only rows keyed by nullable upstream `id`, while v2 also allows superusers to create local bans with `id = NULL` and a UUIDv7 internal identifier; if upstream ever introduces true ban deletions/unbans, the sync policy must be revisited.

### 6.2 Extend Rules
- Keep mirrored source data separate from v2-derived data.
- Build v2-native features (ratings/profile analytics/cache views) on top of mirrored data.
- Keep scope-aware points/rank calculations as v2-owned derived logic.

### 6.3 Contract Rules
- `/v0` is the compatibility contract and must remain stable.
- Compatibility tests guard response shape and behavioral parity.
- New product-native behavior should prefer `/v1` instead of changing `/v0` semantics.
- Bans now have both `/v0/bans` compatibility reads and `/v1/bans` public `{data, count}` reads for future user-facing bans pages.
- `/v0/bans` only returns mirrored GlobalAPI bans with a non-null external id, while `/v1/bans` exposes both `uuid` and nullable external `id`, allows superuser manual creation through `POST /v1/bans`, and uses UUIDs for `/v1/bans/{uuid}` detail reads.
- `/v1/graphql` is an additive read-only surface for selective player hydration and batched map-preview URL resolution; it does not replace `/v0` or remove dedicated `/v1` REST endpoints.
- Touched `/v1` non-player responses should embed compact player references instead of full player payloads when only identity/display name is required inline.

## 7) Engineering Requirements
- Async-first API, DB, and outbound integrations for request paths.
- Strong typing and lint/test gates across backend and frontend.
- Backend coverage target remains >= 90%.
- Clear domain boundaries (sync/mirror, records, rankings, players, maps, servers, auth).
- Health/readiness surfaces for API and background workloads.
- Auditable and observable sync/ingestion behavior.

## 8) UX Requirements
- Shared player avatars and the main profile avatar show bottom-right activity badges: green for fresh tracked public-server presence, blue for recorded play within seven days, and solid gray for at least one year without recorded play. Seven-days-to-one-year gaps and unknown activity have no badge. Tooltips explain the status and respect date/time preferences. Presence is independent of Steam online status, refreshes every 30 seconds, and is omitted from static shareable cards.
- Profile-first product quality bar: information-dense but readable.
- Desktop and mobile support with predictable interactions.
- High-value workflows must be quick: search player, inspect profile, compare rank, open map context, view live server state.
- Public website UI copy should support English, Simplified Chinese, and Russian, with English as the primary source locale.
- Public community content supports Discord-style emoji reactions on media, recent WRs, map-review comments, whole polls, and releases. Guests can inspect totals and reactor identities; authenticated players can independently toggle multiple catalog emoji. Reactions do not create notifications or influence sorting or activity timestamps.

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

## Player setup and gear discovery

- Players optionally publish primary peripherals and PC components from `/settings/setup`, including instantly shared custom models. Product identity verification is an operator task; there is no approval queue or automatic verification schedule.
- Profile Home shows completed setup fields before pinned records, with product names linking to a web search in a new tab.
- CS:GO sensitivity and mouse DPI are manually entered; eDPI is calculated as their product and omitted when either is absent. Memory configuration can be shared without a kit model.
- `/leaderboards/gear` ranks current category selections by distinct players, with percentages based on all participants in that category regardless of search or pagination. Community-added models count; configuration-only memory rows do not.
- The catalog contains over 2,400 models across all 13 categories with manufacturer sources and research dates; seed choices are not claimed as GOKZ usage statistics. Product images are out of scope.

- Add-product dialogs explicitly show their fixed gear category and filter suggestions accordingly. Brand choices come from verified canonical catalog products, with an explicit missing-brand fallback. Optional HTTP/HTTPS product URLs are recorded in the existing operator audit log (including duplicate submissions), never fetched; `kztop products references` lists them for review and resolves merged products. No additional database migration is needed.

- Setup product searches dismiss on outside pointer/focus changes. The brands endpoint requires a gear category and lists only verified brands in that category. Custom-product required fields use red asterisks; setup editing omits memory speed and retains existing stored speed when saving a retained memory entry.

- Setup editing displays selected products inside clearable search inputs. Brand selection is searchable with the missing-brand choice first. DPI and refresh-rate controls sit beside mouse/monitor, while memory model, capacity, and type share a responsive row.

- Product catalog revision 4 contains 2,451 models, retaining the NuPhy/Ryzen/Chinese-market additions and expanding thin GPU, CPU, monitor, PSU, storage, case, and peripheral categories. The versioned products.coverage.v4.json records category counts and complete coverage of 81 explicitly named discrete GPU identifiers in the September 2026 Steam survey main table. Steam is a GPU coverage reference, not an exact CPU/peripheral model source or GOKZ usage ranking. Chinese brand/model aliases and R5/R7 shorthand are seeded; category-scoped curated brands are available after the idempotent operator import.

- Setup replacement supports top-level operating_system stored in player_game_settings and positive storage_capacity_gb in player_hardware (including capacity-only storage). Additive migration 98ea05caeefd introduces nullable columns. Profile setup editing is in the card header, product links omit community badges/underlines, setup-related tabs are last, and the gear leaderboard omits search and descriptive participation text.

- Migration 89e9355f393f preserves storage_capacity_unit (GB/TB, existing entries default GB) alongside integer GB capacity. Editor converts using decimal storage units (1 TB = 1000 GB); public setup respects the saved unit. Points distributions render only on profile Stats via ProfileRecordDistributionSection; gear categories appear as wrapping buttons above the leaderboard table, defaulting to Mouse; the title and category dropdown are removed.

## Profile first completion dates

- `/profile/:identifier/runs` offers an opt-in Show first completion time column, sortable across the full loaded PB list. Dates reflect the earliest valid recorded finish per map/course within the selected scope; NUB includes any teleport count, PRO requires zero teleports, and KZT includes NKZ. Existing PB dates and date filters retain their meaning. Missing first-completion dates sort last.
- The option resets when leaving Runs, changing player, or reloading to limit expensive initial history reads. Presets never enable it. Loading and retryable failures leave ordinary PB rows available, and displayed datetimes respect viewer date and clock preferences.

## Shareable player cards

- The official QQ bot generates portrait cards from `/cards/player/:identifier`, with player identity/country flag, rating icon/global and regional standings/total points, long-jump personal best, NUB completion, and the relative six-skill radar. Cards omit site branding, Steam IDs, and URLs, support OVR/KZT/SKZ/VNL and English/Chinese/Russian, and do not trigger profile-view writes or player synchronization. Images are cached in the bot for 15 minutes; forced image regeneration is separate from player-data refresh.


Rating.E uses the best 100 validated main-course maps in tiers 1–4; Rating.H uses the best 50 in tiers 5–8. Each map contributes its higher NUB/PRO PB-point value, with the existing 0.975 weighted decay and ten-map player eligibility. Each category has an independent population-calibrated display curve per scope, using the same percentile and tie rules as skill ratings (maximum displayed value 10.99). Eligible unbanned players with zero category rating remain in the calibration population. Missing curves and zero raw ratings return null.

After changing these limits or the formula, run `kztop build rating` across all scopes, preview `kztop build difficulty-converters`, then explicitly save with `kztop build difficulty-converters --save`. Use `--scope` to select a scope. Reads and nightly rebuilds never refresh these curves automatically. Overall rating, total points, and six-skill ratings are unchanged.

- `/maps` supports signed-in personal map discovery: one selected NUB/PRO PB time per image, completion filters consistent with profile preferences, and full-catalog PB sorting. Browser-persisted Options controls card sections; public Metrics includes Bonuses and 1st Med WR Gap, with hover/focus explanations and separate touch information buttons. 1st Med retains its existing median-of-player-bests meaning.

## Direct record submission

- Enabled native servers in validated gokz.top groups can submit normal-style 128-tick VNL, SKZ, KZT, and NKZ finishes without GlobalAPI approval or availability. NKZ retains its own identity while sharing KZT eligibility and KZT/OVR rankings. Native records participate in PBs, WRs, activity, points, and server attribution; legacy mirrored reads remain compatible.
- `!topcheck`/`!tc` report eligibility and queue status without changing `!gc`. Durable uploads retry transient failures, pause authentication failures, retain rejected metadata for root inspection, and cannot migrate silently between API environments or server identities. Optional UUIDv7 preserves AXEKZ local identities.
- Explicit upstream claims require exact statistics and server ownership. Uncertain equal-time runs remain distinct for operator review. Reconciliation preserves canonical UUID aliases and moderation and does not re-emit achievements for identity-only changes.
- Main-course replays require a strict PB and top 50 OVR or top 10 applicable mode rank. Bonuses upload only new WRs. Any qualifying NUB/PRO bucket permits one upload; ties do not improve records. Qualification persists across retries and later rank changes. Replay failures never undo accepted records, and historical replays remain available.
- Replay availability is a durable database catalog. Public reads and lists never probe or list object storage. Historical disk files use a resumable one-time backfill; external storage changes use explicit bounded reconciliation. Roll out migrations and backfill before catalog reads and plugin enablement.

- Server plugins automatically identify instances using authenticated server SteamID64, following AXEKZ. Group-key heartbeats register identity and track address changes, with unique ownership and preserved internal UUID/history. Records accept SteamIDs or legacy UUIDs and retry pending registration. No operator-set instance ID or per-instance verification is required; group validation and moderation remain enforced.

- `/servers` presents independent GlobalAPI/gokz.top readiness sections; online badges turn green for either eligible service. Authenticated heartbeat `gokz_top_status` carries records-plugin evidence and mode versions, validated by the backend and persisted inside the existing status JSON (no schema migration). Public live status exposes a separate direct status including NKZ/KZT filter sharing. Missing evidence clears readiness.

- In-game main-course PB feedback compares finishes against gokz.top, with positive red gaps for slower runs and negative green gaps for improvements. New PBs display matching accepted time, points, point gain when known, and date; delayed uploads resume refreshes without reusing stale metadata. NKZ uses KZT PB rankings. Obsolete comparisons are cancelled on disconnect, map change, or API environment change.

- Direct record acceptance atomically advances player date bounds, rebuilds the submitting player’s applicable leaderboard totals/PB contributions, and invalidates non-daily activity aggregates (including historical cursors). Server receipt time marks record updates so delayed runs remain visible to incremental jobs. Player-filtered OVR events refresh profile metadata on every tab regardless of selected scope. Bounded `python -m app.record_player_metadata [--apply] --limit N --after STEAMID` repairs previously accepted native players without changing identity fields or emitting runs.

- The records plugin skips known unsupported finishes before queuing and rechecks exact 128-tick map/course filters before uploading in all modes, with NKZ sharing KZT and zero-teleport runs qualifying through NUB or PRO. Environment-specific filter caches persist across reloads and refresh every minute; unknown availability waits without uploading. Unsupported unacknowledged jobs, including old rejections, are pruned with only their private replay copies. Acknowledged jobs and non-filter failures remain intact.

- Replay playback resolves public download URLs before fetching R2 objects directly, retaining explicit viewer-origin CORS rules across the download flow. Legacy download links, UUID aliases, and disk replays remain supported.

- Map name pronunciations use backend-only ElevenLabs Lauren (`DODLEQrClDo8wCz460ld`), Eleven v4, and immutable R2 MP3 clips. Persistent per-map jobs generate existing maps on first playback and queue newly imported maps atomically, with advisory-locked processing, bounded retries, and credential/credit pause recovery. Public GET/POST `/v1/maps/{map_id}/pronunciation` expose status and ready URLs; shared map menus and the map detail title provide single-stream playback. Spoken names omit known prefixes, underscores, and technical suffixes while preserving `final`/numbered final tokens. No catalog backfill or frontend provider credentials.


- Player pronunciation uses the current stored alias/name with Unicode cleanup and on-demand generation only. Maps and players share one provider-locked worker, pause state, audio controller, and R2 storage pipeline. Public `/v1/players/{identifier}/pronunciation` never refreshes Steam. Admin/superuser pronunciation dialogs support voice, automatic/explicit language, and custom speech text; map admins are restricted to maps. Persistent per-target overrides survive normal playback and reset after a cleaned source-name change. `/v1/admin/pronunciations/options` reads cached backend-only provider choices; synthesis model selection remains operational configuration, not an editor control.

- Player setup migration `30fd121073fa` preserves existing selections in JSONB, supports multiple disks and decimal monitor sizes in inches, and tracks setup creation/edit times in the database only (legacy baseline is migration time); these timestamps are excluded from setup API responses and UI. Setup responses keep the hardware array contract. Storage rankings and operator usage counts deduplicate by player/product, with distinct category participants as denominator. Profile setup uses compact rows, Monitor/Mouse/Mouse Pad/Keyboard/Headset order, and CS:GO settings under Peripherals.

- The official QQ bot supports GOKZ only (OVR/KZT/SKZ/VNL). Game-selection commands and CS2KZ integrations are removed. Startup Alembic migrations upgrade the bot’s SQLite user table while preserving Steam bindings and GOKZ preferences.

- Shared map overview cards show at most six skill legend entries (the bar retains all portions), average finishes and recorded run time per player, and separate median-PB and chronological first-completion times/gaps. WR gaps display run-time/WR multipliers site-wide, including 1.00x for equal WR times, with two truncated decimals through 10x and one above 10x. NUB/PRO distribution chart shapes remain unchanged; only gap labels convert to multipliers.

- Direct records and GlobalAPI sync acquire course locks before player rows/upstream identities, bound lock waits to five seconds, and retry transient direct transactions through durable receipts. Steam fetches, replay request streams and R2 writes release pooled connections during network I/O; replay catalog acknowledgement revalidates eligibility/checksums. Existing records plugins can deduplicate via unique same-group, same-statistics, five-second matches with receipt-capped future clocks and the legacy ±1 ms runtime difference. When a client clock is more than five seconds ahead of receipt time, queued delivery may match upstream timestamps from 30 seconds before receipt through five seconds after it, requiring runtime >35 seconds and bidirectional uniqueness. Ordinary runs <=10 seconds, longer delays, and ambiguous/historical pairs require explicit identity. Both ingestion orders preserve native UUIDs, original receipts, aliases, moderation and replay keys without duplicate notifications. Bounded `app.record_identities --reconcile-compatible [--apply] --limit N --after RECEIPT_UUID` repairs existing pairs. Records plugin1.0.2 reads GlobalAPI `record_id` and follows its full-float serialization/millisecond truncation.

- Server-group API-key usage stamps commit at the authentication boundary before business writes and skip administratively locked rows. This prevents a shared key from serializing heartbeat, record, replay, jumpstat, and map-review requests behind a slow ingest transaction.

- The uploader and PB announcement core share `GOKZTop_FormatRecordTime`; upgrade them together to align accepted-time acknowledgements, new-PB detection and fresh point gains with GlobalAPI millisecond truncation.

- Identity attachment and GlobalAPI sync use non-blocking initial course locks and retry whole transactions after releasing pooled connections. Exhausted attachment retries and pool exhaustion return 503 with Retry-After; busy upstream records defer without advancing their cursor. Compatibility accepts ±1 ms in either direction, checks each direction’s full candidate range, and preserves ambiguity guards, supplied UUIDs, aliases, receipts, moderation, replay metadata, and PB precision.

- Replay eligibility predicates use `Record.is_valid == true()` to match the record table’s partial indexes; `IS true` prevents those indexes from satisfying the query and causes long full-table scans while holding the course lock.

- Frozen replay-policy alternatives for late upstream claims use each candidate’s canonical runtime and the symmetric ±1 ms candidate range, preserving strict PB/WR rules across either rounding direction.

- PB bucket winner selection and map leaderboard refreshes use the same literal `is_valid = true` partial-index predicate as replay qualification. A database-plan regression exercises both write refresh paths and requires partial course indexes.

## Map preview delivery

- Serve the complete upstream WebP collection from persistent local storage, syncing at startup when due and every 24 hours after success. Retry failures after one hour without removing existing images.
- Cache successful image responses in browsers and Cloudflare for seven days; keep stable URLs and do not purge automatically. Missing images are not cached.
- Prefer local previews across map, profile, record, and server surfaces. Use direct Steam Workshop previews for missing or failed local images, loading only one source at a time; retain placeholders when no image is available.

- `/maps` provides browser-local named presets (up to 20) for scope, NUB/PRO, catalog filters, sorting, and card options; applying resets pagination to page one. Presets are independent of profile Runs and use validated, versioned localStorage with save-error feedback.

- `/maps` and profile Runs independently save optional browser-local default-view snapshots from their Presets menus. Validated versioned defaults load on mount; maps defaults supersede session state and restore scope/card options from page one. Clearing removes only the default, and Runs defaults never activate first-completion history reads.

- Profile Activity and total playtime share versioned daily cache data combining merged completed player sessions and record runtimes whose finish timestamps fall outside those sessions (inclusive endpoints). Sessions split at UTC midnight; open sessions are excluded until disconnect/timeout. Daily entries retain record counts and add total_seconds. Session closure invalidates the shared cache; record mutations refresh affected days. Calendar colors use view-relative positive-duration quartiles. Server/map breakdowns remain record-based.

## Shared QQ and Discord Bot

- QQ and Discord expose GOKZ command features through one NoneBot application. Discord uses Alconna; QQ preserves its original response handlers, help image, command panel, Chinese Markdown, keyboards, aliases, and button actions exactly as before the refactor. Discord uses English slash commands, embeds, buttons, and player cards. QQ-only rendering diagnostics and automatic voice compliments remain platform-specific.
- Discord users initially bind using the existing website binding-code page and `/bind code:<code>`, with a private reply. This is independent of website Discord social links and requires no website deployment. Preferences and daily maps remain independent per platform account.
- Discord interactive controls are restricted to the requesting user and expire after ten minutes or restart. Discord acknowledges slow commands immediately; binding and account-connection errors remain private. Root identities are platform-qualified, and server defaults apply to QQ groups or Discord guilds.

- Discord `/profile` remains usable when optional enrichment is unavailable, with a partial-data warning instead of a site-outage error. Profile, rank, and server replies use rich layouts; warnings and errors have distinct colours, and `/pr` shows relative dates.
