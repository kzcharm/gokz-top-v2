import { OpenAPI, type ServerPublic } from "@/client"
import { getCountryName } from "@/components/Common/CountryFlag"

import { normalizeTierValue } from "./tier"

export type ServerStatusFilter = "online" | "offline"
export type ServerViewMode = "grid" | "table"
export type ServerSortKey = "players" | "hostname" | "map" | "tier"
export type ServerSortDirection = "asc" | "desc"
export type ServerPlayer = Record<string, unknown>

export interface ServersSearchState {
  q: string
  status: ServerStatusFilter
  country: string
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
  country: "all",
  view: "grid",
  sort: "players",
  dir: "desc",
}

export const SERVER_CONFIG_FILENAME = "servers.cfg"

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
  const rawCountry =
    typeof search.country === "string"
      ? search.country.trim().toUpperCase()
      : ""
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
    country:
      rawCountry && rawCountry !== "ALL"
        ? rawCountry
        : DEFAULT_SERVERS_SEARCH.country,
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
    ["country", normalizedSearch.country, DEFAULT_SERVERS_SEARCH.country],
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

export function getServerAddress(server: ServerPublic) {
  return `${server.ip}:${server.port}`
}

export function getServerHostname(server: ServerPublic) {
  return server.live_status?.hostname?.trim() || getServerAddress(server)
}

export function getServerMapName(server: ServerPublic) {
  return server.live_status?.map?.trim() || null
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

export function getServerPlayerCount(server: ServerPublic) {
  return server.live_status?.player_count ?? 0
}

export function getServerMaxPlayers(server: ServerPublic) {
  return server.live_status?.max_players ?? 0
}

export function isServerStatusRefreshing(server: ServerPublic) {
  if (!isServerOnline(server)) {
    return false
  }

  const lastA2SSeenAt = server.live_status?.last_a2s_seen_at
  const lastSuccessfulSeenAt = server.live_status?.last_successful_seen_at
  if (!lastA2SSeenAt || !lastSuccessfulSeenAt) {
    return false
  }

  return Date.parse(lastA2SSeenAt) > Date.parse(lastSuccessfulSeenAt)
}

export function getServerLocation(server: ServerPublic) {
  return [server.city, server.country].filter(Boolean).join(", ")
}

export function getServerMapImageUrl(mapName: string | null) {
  if (!mapName) {
    return null
  }

  return `https://github.com/KZGlobalTeam/map-images/raw/public/webp/${mapName}.webp`
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
  if (!pathname.startsWith("/servers/")) {
    return null
  }

  return decodeURIComponent(pathname.slice("/servers/".length))
}

export function matchesServerSearch(server: ServerPublic, rawQuery: string) {
  const query = rawQuery.trim().toLowerCase()
  if (!query) {
    return true
  }

  const fields = [
    getServerAddress(server),
    server.ip,
    String(server.port),
    getServerHostname(server),
    getServerMapName(server),
    server.city,
    server.country,
    getCountryName(server.country),
    server.group?.name,
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

export function getCountryCounts(
  servers: ServerPublic[],
  statusFilter: ServerStatusFilter,
) {
  const counts = new Map<string, number>()

  for (const server of servers) {
    if (!matchesServerStatusFilter(server, statusFilter)) {
      continue
    }

    const country = server.country?.toUpperCase()
    if (!country) {
      continue
    }

    counts.set(country, (counts.get(country) || 0) + 1)
  }

  return Array.from(counts.entries()).sort((left, right) =>
    left[0].localeCompare(right[0]),
  )
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
    case "paused":
      return "Paused"
    case "aborted":
      return "Aborted"
    default:
      return "Unknown"
  }
}

export function getPlayerStatusSurfaceClass(player: ServerPlayer) {
  const status = getPlayerStringValue(player, "status")
  const teleports = getPlayerNumberValue(player, "teleports") || 0

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
    case "paused":
      return {
        backgroundClassName: "bg-orange-200 dark:bg-orange-900/60",
        badgeClassName: "bg-orange-600 text-white",
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

export function formatTimerTime(seconds: number | null) {
  if (seconds === null) {
    return "-"
  }

  const totalSeconds = Math.floor(seconds)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const secs = totalSeconds % 60

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${secs
      .toString()
      .padStart(2, "0")}`
  }

  return `${minutes}:${secs.toString().padStart(2, "0")}`
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
