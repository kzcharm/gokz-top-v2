import { OpenAPI, type ServerPublic } from "@/client"
import { getCountryName } from "@/components/Common/CountryFlag"
import { getWorkshopPreviewImageUrl as getCommonWorkshopPreviewImageUrl } from "@/components/Common/MapDisplay"
import { getRegionName } from "@/components/Common/RegionFlag"

import { normalizeTierValue } from "./tier"

export type ServerStatusFilter = "online" | "offline"
export type ServerViewMode = "grid" | "table"
export type ServerSortKey = "players" | "hostname" | "map" | "tier"
export type ServerSortDirection = "asc" | "desc"
export type ServerPlayer = NonNullable<
  NonNullable<ServerPublic["live_status"]>["players"]
>[number] &
  Record<string, unknown>

export interface ServersSearchState {
  q: string
  status: ServerStatusFilter
  group: string
  region: string
  view: ServerViewMode
  sort: ServerSortKey
  dir: ServerSortDirection
}

export type ServerRealtimeEvent =
  | {
      type: "server.snapshot"
      servers: ServerPublic[]
    }
  | {
      type: "server.updated"
      server: ServerPublic
    }

export const DEFAULT_SERVERS_SEARCH: ServersSearchState = {
  q: "",
  status: "online",
  group: "all",
  region: "all",
  view: "grid",
  sort: "players",
  dir: "desc",
}

export const SERVER_CONFIG_FILENAME = "servers.cfg"
export const UNASSIGNED_SERVER_GROUP_ID = "unassigned"
export const UNASSIGNED_SERVER_GROUP_CUSTOM_ID = "others"
export const UNASSIGNED_SERVER_GROUP_NAME = "Others"
const SERVERS_FILTER_PREFERENCES_STORAGE_KEY = "gokz-server-browser-filters"
const SERVERS_FILTER_PREFERENCES_VERSION = 1
const PINNED_SERVER_GROUP_NAMES = ["AXE GOKZ"]

interface ServersFilterPreferences {
  version: typeof SERVERS_FILTER_PREFERENCES_VERSION
  group: string
  region: string
  sort?: ServerSortKey
  dir?: ServerSortDirection
}

interface CreateServersSearchParamsOptions {
  includeDefaults?: boolean
}

function isServerStatusFilter(value: unknown): value is ServerStatusFilter {
  return value === "online" || value === "offline"
}

function isServerViewMode(value: unknown): value is ServerViewMode {
  return value === "grid" || value === "table"
}

function isServerSortKey(value: unknown): value is ServerSortKey {
  return (
    value === "players" ||
    value === "hostname" ||
    value === "map" ||
    value === "tier"
  )
}

function isServerSortDirection(value: unknown): value is ServerSortDirection {
  return value === "asc" || value === "desc"
}

export function normalizeServersSearch(
  search: Record<string, unknown>,
): ServersSearchState {
  const rawRegion =
    typeof search.region === "string" ? search.region.trim().toUpperCase() : ""
  const rawGroup = typeof search.group === "string" ? search.group.trim() : ""
  const rawStatus =
    typeof search.status === "string" ? search.status.trim().toLowerCase() : ""

  return {
    q: typeof search.q === "string" ? search.q : DEFAULT_SERVERS_SEARCH.q,
    status:
      rawStatus === "all"
        ? "offline"
        : isServerStatusFilter(rawStatus)
          ? rawStatus
          : DEFAULT_SERVERS_SEARCH.status,
    group:
      rawGroup && rawGroup.toLowerCase() !== "all"
        ? rawGroup
        : DEFAULT_SERVERS_SEARCH.group,
    region:
      rawRegion && rawRegion !== "ALL"
        ? rawRegion
        : DEFAULT_SERVERS_SEARCH.region,
    view: isServerViewMode(search.view)
      ? search.view
      : DEFAULT_SERVERS_SEARCH.view,
    sort: isServerSortKey(search.sort)
      ? search.sort
      : DEFAULT_SERVERS_SEARCH.sort,
    dir: isServerSortDirection(search.dir)
      ? search.dir
      : DEFAULT_SERVERS_SEARCH.dir,
  }
}

export function createServersSearchParams(
  search: ServersSearchState,
  options: CreateServersSearchParamsOptions = {},
) {
  const normalizedSearch = normalizeServersSearch({ ...search })
  const { includeDefaults = false } = options
  const params = new URLSearchParams()

  const entries = [
    ["q", normalizedSearch.q, DEFAULT_SERVERS_SEARCH.q],
    ["status", normalizedSearch.status, DEFAULT_SERVERS_SEARCH.status],
    ["group", normalizedSearch.group, DEFAULT_SERVERS_SEARCH.group],
    ["region", normalizedSearch.region, DEFAULT_SERVERS_SEARCH.region],
    ["view", normalizedSearch.view, DEFAULT_SERVERS_SEARCH.view],
    ["sort", normalizedSearch.sort, DEFAULT_SERVERS_SEARCH.sort],
    ["dir", normalizedSearch.dir, DEFAULT_SERVERS_SEARCH.dir],
  ] as const

  for (const [key, value, defaultValue] of entries) {
    if (includeDefaults || value !== defaultValue) {
      params.set(key, value)
    }
  }

  return params
}

function getStorage() {
  return typeof window === "undefined" ? null : window.localStorage
}

export function readServersFilterPreferences() {
  const storage = getStorage()
  if (!storage) {
    return null
  }

  try {
    const rawPreferences = storage.getItem(
      SERVERS_FILTER_PREFERENCES_STORAGE_KEY,
    )
    if (!rawPreferences) {
      return null
    }

    const preferences = JSON.parse(
      rawPreferences,
    ) as Partial<ServersFilterPreferences>
    if (preferences.version !== SERVERS_FILTER_PREFERENCES_VERSION) {
      return null
    }

    return {
      group: normalizeServersSearch({ group: preferences.group }).group,
      region: normalizeServersSearch({ region: preferences.region }).region,
      sort: normalizeServersSearch({ sort: preferences.sort }).sort,
      dir: normalizeServersSearch({ dir: preferences.dir }).dir,
    }
  } catch {
    return null
  }
}

export function writeServersFilterPreferences(
  search: Pick<ServersSearchState, "group" | "region" | "sort" | "dir">,
) {
  const storage = getStorage()
  if (!storage) {
    return
  }

  try {
    const preferences: ServersFilterPreferences = {
      version: SERVERS_FILTER_PREFERENCES_VERSION,
      group: normalizeServersSearch({ group: search.group }).group,
      region: normalizeServersSearch({ region: search.region }).region,
      sort: normalizeServersSearch({ sort: search.sort }).sort,
      dir: normalizeServersSearch({ dir: search.dir }).dir,
    }

    if (
      preferences.group === DEFAULT_SERVERS_SEARCH.group &&
      preferences.region === DEFAULT_SERVERS_SEARCH.region &&
      preferences.sort === DEFAULT_SERVERS_SEARCH.sort &&
      preferences.dir === DEFAULT_SERVERS_SEARCH.dir
    ) {
      storage.removeItem(SERVERS_FILTER_PREFERENCES_STORAGE_KEY)
      return
    }

    storage.setItem(
      SERVERS_FILTER_PREFERENCES_STORAGE_KEY,
      JSON.stringify(preferences),
    )
  } catch {
    // Ignore storage failures so private browsing or quota issues do not break filtering.
  }
}

export function getServerAddress(server: ServerPublic) {
  return `${server.ip}:${server.port}`
}

export function getServerGroupId(server: ServerPublic) {
  return server.group_id ?? null
}

export function getServerGroupName(server: ServerPublic) {
  return server.group?.name?.trim() || null
}

export function getServerGroupCustomId(server: ServerPublic) {
  return server.group?.custom_id?.trim() || null
}

export function getServerHostname(server: ServerPublic) {
  return server.live_status?.hostname?.trim() || getServerAddress(server)
}

export function normalizeServerMapName(mapName: string | null | undefined) {
  if (!mapName) {
    return null
  }

  const normalizedParts = mapName
    .trim()
    .replace(/\\/g, "/")
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean)

  return normalizedParts[normalizedParts.length - 1] ?? null
}

export function getServerMapName(server: ServerPublic) {
  return normalizeServerMapName(server.live_status?.map)
}

export function getServerPlayers(server: ServerPublic) {
  return Array.isArray(server.live_status?.players)
    ? server.live_status.players
    : []
}

export function isServerOnline(server: ServerPublic) {
  return server.live_status?.is_online ?? false
}

export function matchesServerStatusFilter(
  server: ServerPublic,
  statusFilter: ServerStatusFilter,
) {
  return statusFilter === "online"
    ? isServerOnline(server)
    : !isServerOnline(server)
}

export function matchesServerGroupFilter(
  server: ServerPublic,
  groupFilter: string,
) {
  if (groupFilter === "all") {
    return true
  }

  if (groupFilter === UNASSIGNED_SERVER_GROUP_ID) {
    return getServerGroupId(server) === null
  }

  return getServerGroupId(server) === groupFilter
}

export function getServerPlayerCount(server: ServerPublic) {
  return server.live_status?.player_count ?? 0
}

export function getServerMaxPlayers(server: ServerPublic) {
  return server.live_status?.max_players ?? 0
}

const SERVER_STATUS_STALE_AFTER_MS = 60_000

export function isServerStatusRefreshing(server: ServerPublic) {
  if (!isServerOnline(server)) {
    return false
  }

  const lastA2SSeenAt = server.live_status?.state?.last_a2s_seen_at
  const lastPluginSeenAt = server.live_status?.state?.last_plugin_seen_at
  const lastSuccessfulSeenAt =
    server.live_status?.state?.last_successful_seen_at
  if (lastA2SSeenAt && lastSuccessfulSeenAt) {
    const lastA2SSeenAtMs = Date.parse(lastA2SSeenAt)
    const lastSuccessfulSeenAtMs = Date.parse(lastSuccessfulSeenAt)
    if (
      Number.isFinite(lastA2SSeenAtMs) &&
      Number.isFinite(lastSuccessfulSeenAtMs) &&
      lastA2SSeenAtMs > lastSuccessfulSeenAtMs
    ) {
      return true
    }
  }

  const observedTimes = [
    lastA2SSeenAt,
    lastPluginSeenAt,
    server.live_status?.updated_at,
  ]
    .map((value) => (value ? Date.parse(value) : Number.NaN))
    .filter((value) => Number.isFinite(value))

  if (observedTimes.length === 0) {
    return false
  }

  return (
    server.status === "invalid" &&
    Date.now() - Math.max(...observedTimes) > SERVER_STATUS_STALE_AFTER_MS
  )
}

export function getServerLastSuccessfulQueryAt(server: ServerPublic) {
  return server.live_status?.state?.last_successful_seen_at ?? null
}

export function getServerLocation(server: ServerPublic) {
  return [server.city, server.country].filter(Boolean).join(", ")
}

export function getServerMapImageUrl(mapName: string | null) {
  const normalizedMapName = normalizeServerMapName(mapName)
  if (!normalizedMapName) {
    return null
  }

  return `https://github.com/KZGlobalTeam/map-images/raw/public/webp/${normalizedMapName}.webp`
}

export function getWorkshopPreviewImageUrl(workshopId: string | null) {
  return getCommonWorkshopPreviewImageUrl(workshopId)
}

export function getServerMapImageUrls(server: ServerPublic) {
  const urls = [
    getServerMapImageUrl(getServerMapName(server)),
    getWorkshopPreviewImageUrl(server.live_status?.workshop_id ?? null),
  ]

  return urls.filter((url): url is string => Boolean(url))
}

export function buildServersWebSocketUrl() {
  const configuredBase = OpenAPI.BASE || window.location.origin
  const baseUrl = new URL(configuredBase, window.location.origin)
  const protocol = baseUrl.protocol === "https:" ? "wss:" : "ws:"
  const normalizedPath =
    baseUrl.pathname === "/" ? "" : baseUrl.pathname.replace(/\/$/, "")

  return `${protocol}//${baseUrl.host}${normalizedPath}/v1/ws/servers`
}

export function getSelectedServerAddress(pathname: string) {
  if (
    !pathname.startsWith("/servers/") ||
    pathname.startsWith("/servers/group/")
  ) {
    return null
  }

  return decodeURIComponent(pathname.slice("/servers/".length))
}

export function getSelectedServerGroupCustomId(pathname: string) {
  if (!pathname.startsWith("/servers/group/")) {
    return null
  }

  return decodeURIComponent(pathname.slice("/servers/group/".length))
}

export function matchesServerSearch(server: ServerPublic, rawQuery: string) {
  const query = rawQuery.trim().toLowerCase()
  if (!query) {
    return true
  }

  const playerNames = getServerPlayers(server)
    .map((player) => getPlayerStringValue(player, "name"))
    .filter((name): name is string => name !== null)

  const fields = [
    getServerAddress(server),
    server.ip,
    String(server.port),
    getServerHostname(server),
    getServerMapName(server),
    server.city,
    server.country,
    getCountryName(server.country),
    server.region,
    getRegionName(server.region),
    server.group?.name,
    server.group?.custom_id,
    ...playerNames,
  ]

  return fields.some((field) => field?.toLowerCase().includes(query))
}

export function sortServers(
  servers: ServerPublic[],
  sortKey: ServerSortKey,
  sortDirection: ServerSortDirection,
) {
  const direction = sortDirection === "asc" ? 1 : -1

  return [...servers].sort((left, right) => {
    let comparison = 0

    switch (sortKey) {
      case "hostname":
        comparison = getServerHostname(left).localeCompare(
          getServerHostname(right),
        )
        break
      case "map":
        comparison = (getServerMapName(left) || "").localeCompare(
          getServerMapName(right) || "",
        )
        break
      case "tier":
        comparison =
          (normalizeTierValue(left.map_tier) ?? -1) -
          (normalizeTierValue(right.map_tier) ?? -1)
        break
      default:
        comparison = getServerPlayerCount(left) - getServerPlayerCount(right)
        break
    }

    if (comparison !== 0) {
      return comparison * direction
    }

    return getServerHostname(left).localeCompare(getServerHostname(right))
  })
}

export function countOnlineServers(servers: ServerPublic[]) {
  return servers.filter(isServerOnline).length
}

export function countOnlinePlayers(servers: ServerPublic[]) {
  return servers.reduce((total, server) => {
    if (!isServerOnline(server)) {
      return total
    }

    return total + getServerPlayerCount(server)
  }, 0)
}

export function getRegionCounts(
  servers: ServerPublic[],
  statusFilter: ServerStatusFilter,
) {
  const counts = new Map<string, { count: number; playerCount: number }>()

  for (const server of servers) {
    if (!matchesServerStatusFilter(server, statusFilter)) {
      continue
    }

    const region = server.region?.toUpperCase()
    if (!region) {
      continue
    }

    const current = counts.get(region)
    const playerCount = isServerOnline(server)
      ? getServerPlayerCount(server)
      : 0
    counts.set(region, {
      count: (current?.count || 0) + 1,
      playerCount: (current?.playerCount || 0) + playerCount,
    })
  }

  return Array.from(counts.entries()).sort((left, right) =>
    left[0].localeCompare(right[0]),
  )
}

function isPinnedServerGroupName(groupName: string) {
  const normalizedGroupName = groupName.trim().toUpperCase()

  return PINNED_SERVER_GROUP_NAMES.includes(normalizedGroupName)
}

export function getServerGroupCounts(
  servers: ServerPublic[],
  statusFilter: ServerStatusFilter,
) {
  const counts = new Map<
    string,
    {
      count: number
      customId: string | null
      name: string
      playerCount: number
    }
  >()

  for (const server of servers) {
    const groupId = getServerGroupId(server)
    const groupName = getServerGroupName(server)
    if (!groupId || !groupName) {
      if (groupId) {
        continue
      }

      const current = counts.get(UNASSIGNED_SERVER_GROUP_ID)
      const matchesStatus = matchesServerStatusFilter(server, statusFilter)
      const playerCount =
        matchesStatus && isServerOnline(server)
          ? getServerPlayerCount(server)
          : 0
      counts.set(UNASSIGNED_SERVER_GROUP_ID, {
        count: (current?.count || 0) + (matchesStatus ? 1 : 0),
        customId: UNASSIGNED_SERVER_GROUP_CUSTOM_ID,
        name: UNASSIGNED_SERVER_GROUP_NAME,
        playerCount: (current?.playerCount || 0) + playerCount,
      })
      continue
    }

    const current = counts.get(groupId)
    const playerCount =
      matchesServerStatusFilter(server, statusFilter) && isServerOnline(server)
        ? getServerPlayerCount(server)
        : 0
    counts.set(groupId, {
      count:
        (current?.count || 0) +
        (matchesServerStatusFilter(server, statusFilter) ? 1 : 0),
      customId: current?.customId ?? getServerGroupCustomId(server),
      name: groupName,
      playerCount: (current?.playerCount || 0) + playerCount,
    })
  }

  return Array.from(counts.entries())
    .sort((left, right) => {
      const unassignedComparison =
        Number(left[0] === UNASSIGNED_SERVER_GROUP_ID) -
        Number(right[0] === UNASSIGNED_SERVER_GROUP_ID)
      if (unassignedComparison !== 0) {
        return unassignedComparison
      }

      const pinnedComparison =
        Number(isPinnedServerGroupName(right[1].name)) -
        Number(isPinnedServerGroupName(left[1].name))
      if (pinnedComparison !== 0) {
        return pinnedComparison
      }

      return left[1].name.localeCompare(right[1].name)
    })
    .filter(([, group]) => group.count > 0)
}

export function getCountryPlayerCounts(servers: ServerPublic[]) {
  const counts = new Map<string, number>()

  for (const server of servers) {
    if (!isServerOnline(server)) {
      continue
    }

    const country = server.country?.toUpperCase()
    if (!country) {
      continue
    }

    counts.set(
      country,
      (counts.get(country) || 0) + getServerPlayerCount(server),
    )
  }

  return counts
}

function sanitizeConfigHostname(hostname: string) {
  return hostname.replace(/\s+/g, " ").trim()
}

function getServerConfigComment(server: ServerPublic, index: number) {
  return `// ${index + 1}. ${sanitizeConfigHostname(getServerHostname(server))}`
}

export function buildServerConfigFile(servers: ServerPublic[]) {
  const sortedServers = [...servers].sort((left, right) =>
    getServerHostname(left).localeCompare(getServerHostname(right)),
  )
  const lines = [
    "// GOKZ.TOP public servers config",
    "// Generated from the current filtered servers browser results.",
    `// Run: exec ${SERVER_CONFIG_FILENAME}`,
    "// Then connect with aliases s1, s2, s3, ...",
    "",
    'echo "GOKZ.TOP server aliases loaded:"',
  ]

  for (const [index, server] of sortedServers.entries()) {
    const hostname = sanitizeConfigHostname(getServerHostname(server))
    lines.push(getServerConfigComment(server, index))
    lines.push(`echo "${index + 1}. ${hostname}"`)
    lines.push(`alias "s${index + 1}" "connect ${getServerAddress(server)}"`)
    lines.push("")
  }

  return `${lines.join("\n").trimEnd()}\n`
}

export function getOccupancyVariant(server: ServerPublic) {
  const playerCount = getServerPlayerCount(server)
  const maxPlayers = getServerMaxPlayers(server)

  if (!isServerOnline(server)) {
    return "bg-gray-500 text-white"
  }

  if (maxPlayers > 0 && playerCount >= maxPlayers) {
    return "bg-red-500 text-white"
  }

  if (playerCount === 0) {
    return "bg-green-500 text-white"
  }

  return "bg-orange-500 text-white"
}

export function getServerSurfaceClass(isSelected: boolean) {
  if (isSelected) {
    return "ring-2 ring-primary shadow-xl [animation:server-selected_650ms_ease-out]"
  }

  return "hover:-translate-y-0.5 hover:shadow-xl hover:ring-1 hover:ring-primary/40"
}

export function getPlayerStringValue(player: ServerPlayer, key: string) {
  const value = player[key]
  return typeof value === "string" && value.trim() !== "" ? value : null
}

export function getPlayerNumberValue(player: ServerPlayer, key: string) {
  const value = player[key]
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

export function getPlayerBooleanValue(player: ServerPlayer, key: string) {
  const value = player[key]
  return typeof value === "boolean" ? value : null
}

export function getPlayerStatusLabel(player: ServerPlayer) {
  const status = getPlayerStringValue(player, "status")

  switch (status) {
    case "not_started":
      return "Not started"
    case "in_progress":
      return "In progress"
    case "finished":
      return "Finished"
    case "aborted":
      return "Aborted"
    default:
      return "Unknown"
  }
}

export function getPlayerStatusSurfaceClass(player: ServerPlayer) {
  const status = getPlayerStringValue(player, "status")
  const teleports = getPlayerNumberValue(player, "teleports") || 0
  const isPaused = getPlayerBooleanValue(player, "is_paused") || false

  if (status === "in_progress" && isPaused) {
    return {
      backgroundClassName: "bg-orange-200 dark:bg-orange-900/60",
      badgeClassName: "bg-orange-600 text-white",
    }
  }

  switch (status) {
    case "not_started":
      return {
        backgroundClassName: "bg-gray-100 dark:bg-gray-700",
        badgeClassName: "bg-gray-500 text-white",
      }
    case "in_progress":
      return teleports > 0
        ? {
            backgroundClassName: "bg-orange-200 dark:bg-orange-900/60",
            badgeClassName: "bg-orange-600 text-white",
          }
        : {
            backgroundClassName: "bg-blue-200 dark:bg-blue-900/60",
            badgeClassName: "bg-blue-600 text-white",
          }
    case "finished":
      return {
        backgroundClassName: "bg-green-200 dark:bg-green-900/60",
        badgeClassName: "bg-green-600 text-white",
      }
    case "aborted":
      return {
        backgroundClassName: "bg-red-200 dark:bg-red-900/60",
        badgeClassName: "bg-red-600 text-white",
      }
    default:
      return {
        backgroundClassName: "bg-gray-100 dark:bg-gray-700",
        badgeClassName: "bg-gray-500 text-white",
      }
  }
}

export function getPlayerAvatarUrl(player: ServerPlayer) {
  const avatarHash = getPlayerStringValue(player, "avatar_hash")
  return avatarHash
    ? `https://avatars.steamstatic.com/${avatarHash}_full.jpg`
    : null
}

export function formatTimerTime(
  seconds: number | null,
  options?: { showDecimals?: boolean },
) {
  if (seconds === null) {
    return "-"
  }

  const { showDecimals = false } = options ?? {}
  const totalSeconds = Math.floor(seconds)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const secs = totalSeconds % 60
  const wholeSeconds = hours > 0 ? totalSeconds % 60 : seconds % 60
  const formattedSeconds = showDecimals
    ? wholeSeconds.toFixed(3).padStart(6, "0")
    : secs.toString().padStart(2, "0")

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${formattedSeconds}`
  }

  return `${minutes}:${formattedSeconds}`
}

export function getPlayerProgressPercent(player: ServerPlayer) {
  const score = getPlayerNumberValue(player, "score")
  if (score === null) {
    return null
  }

  return Math.max(0, Math.min(100, score / 10))
}

export function sortPlayersByProgress(players: ServerPlayer[]) {
  return [...players].sort((left, right) => {
    const rightScore = getPlayerNumberValue(right, "score") || 0
    const leftScore = getPlayerNumberValue(left, "score") || 0
    return rightScore - leftScore
  })
}
