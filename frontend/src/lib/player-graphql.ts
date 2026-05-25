import type { ModeScope, UserRole } from "@/client"
import { requestGraphQL } from "@/lib/graphql"

export type GraphqlPlayer = {
  steamid64: string
  displayName: string
  name: string
  alias: string | null
  customId: string | null
  avatarHash: string | null
  country: string | null
  primaryScope: ModeScope
  rating: number
  roles: UserRole[] | null
  lastPlayedAt: string | null
  createdAt?: string | null
  updatedAt?: string | null
  profileViews?: number
}

type PlayersQueryResponse = {
  players: Array<GraphqlPlayer | null>
}

type SearchPlayersQueryResponse = {
  searchPlayers: {
    count: number
    data: GraphqlPlayer[]
  }
}

type PlayerQueryResponse = {
  player: GraphqlPlayer | null
}

const GRAPHQL_TO_USER_ROLE: Record<string, UserRole> = {
  SUPERUSER: "superuser",
  ADMIN: "admin",
  MAP_ADMIN: "map_admin",
  SERVER_OWNER: "server_owner",
}

type PendingPlayerBatchEntry = {
  reject: (reason?: unknown) => void
  resolve: (player: GraphqlPlayer | null) => void
}

const PLAYER_BATCH_DELAY_MS = 10

const DISPLAY_PLAYER_FIELDS = `
  steamid64
  displayName
  name
  alias
  customId
  avatarHash
  country
  primaryScope
  rating(scope: $scope)
  roles
`

function normalizeGraphqlPlayer(
  player: GraphqlPlayer | null,
): GraphqlPlayer | null {
  if (player === null) {
    return null
  }

  const normalizedRoles =
    player.roles?.map((role) => GRAPHQL_TO_USER_ROLE[role] ?? role) ?? null

  return {
    ...player,
    roles: normalizedRoles,
  }
}

function getDisplayPlayerCacheKey(steamid64: string, scope?: ModeScope) {
  return `${steamid64}:${scope ?? "PRIMARY"}`
}

export async function fetchPlayerByIdentifier(
  identifier: string,
  scope?: ModeScope,
) {
  const response = await requestGraphQL<PlayerQueryResponse>(
    `
      query PlayerByIdentifier($identifier: String!, $scope: ModeScope) {
        player(identifier: $identifier) {
          ${DISPLAY_PLAYER_FIELDS}
          lastPlayedAt
          createdAt
          updatedAt
          profileViews
        }
      }
    `,
    { identifier, scope },
  )

  return normalizeGraphqlPlayer(response.player)
}

async function requestPlayersForDisplay(
  steamid64s: string[],
  scope?: ModeScope,
) {
  if (steamid64s.length === 0) {
    return []
  }

  const response = await requestGraphQL<PlayersQueryResponse>(
    `
      query PlayersForDisplay($steamid64s: [ID!]!, $scope: ModeScope) {
        players(steamid64s: $steamid64s) {
          ${DISPLAY_PLAYER_FIELDS}
          lastPlayedAt
        }
      }
    `,
    { steamid64s, scope },
  )

  return response.players.map((player) => normalizeGraphqlPlayer(player))
}

let pendingPlayerBatch = new Map<string, PendingPlayerBatchEntry[]>()
let pendingPlayerBatchTimer: ReturnType<typeof setTimeout> | null = null
const cachedDisplayPlayers = new Map<string, GraphqlPlayer | null>()
const inflightDisplayPlayers = new Map<string, Promise<GraphqlPlayer | null>>()

function queuePlayerBatchLoad(steamid64: string, scope?: ModeScope) {
  const cacheKey = getDisplayPlayerCacheKey(steamid64, scope)
  const existingPromise = inflightDisplayPlayers.get(cacheKey)
  if (existingPromise) {
    return existingPromise
  }

  const promise = new Promise<GraphqlPlayer | null>((resolve, reject) => {
    const existingResolvers = pendingPlayerBatch.get(cacheKey) ?? []
    existingResolvers.push({ resolve, reject })
    pendingPlayerBatch.set(cacheKey, existingResolvers)

    if (pendingPlayerBatchTimer !== null) {
      return
    }

    pendingPlayerBatchTimer = setTimeout(() => {
      void flushPendingPlayerBatch()
    }, PLAYER_BATCH_DELAY_MS)
  })

  inflightDisplayPlayers.set(cacheKey, promise)
  return promise
}

async function flushPendingPlayerBatch() {
  const currentBatch = pendingPlayerBatch
  pendingPlayerBatch = new Map()
  pendingPlayerBatchTimer = null

  const requestsByScope = new Map<ModeScope | undefined, string[]>()
  for (const cacheKey of currentBatch.keys()) {
    const [steamid64, scopeKey] = cacheKey.split(":")
    const scope = scopeKey === "PRIMARY" ? undefined : (scopeKey as ModeScope)
    const existingSteamid64s = requestsByScope.get(scope) ?? []
    existingSteamid64s.push(steamid64)
    requestsByScope.set(scope, existingSteamid64s)
  }

  try {
    for (const [scope, steamid64s] of requestsByScope) {
      const players = await requestPlayersForDisplay(steamid64s, scope)
      steamid64s.forEach((steamid64, index) => {
        const cacheKey = getDisplayPlayerCacheKey(steamid64, scope)
        const resolvers = currentBatch.get(cacheKey) ?? []
        const player = players[index] ?? null
        cachedDisplayPlayers.set(cacheKey, player)
        inflightDisplayPlayers.delete(cacheKey)
        for (const entry of resolvers) {
          entry.resolve(player)
        }
      })
    }
  } catch (error) {
    for (const cacheKey of currentBatch.keys()) {
      inflightDisplayPlayers.delete(cacheKey)
    }
    for (const resolvers of currentBatch.values()) {
      for (const entry of resolvers) {
        entry.reject(error)
      }
    }
  }
}

export async function fetchPlayersForDisplay(
  steamid64s: string[],
  scope?: ModeScope,
) {
  if (steamid64s.length === 0) {
    return []
  }

  const uncachedSteamid64s = steamid64s.filter(
    (steamid64) =>
      !cachedDisplayPlayers.has(getDisplayPlayerCacheKey(steamid64, scope)),
  )

  await Promise.all(
    uncachedSteamid64s.map((steamid64) =>
      queuePlayerBatchLoad(steamid64, scope),
    ),
  )

  return steamid64s.map(
    (steamid64) =>
      cachedDisplayPlayers.get(getDisplayPlayerCacheKey(steamid64, scope)) ??
      null,
  )
}

export async function loadPlayerForDisplay(
  steamid64: string,
  scope?: ModeScope,
) {
  const [player] = await fetchPlayersForDisplay([steamid64], scope)
  return player ?? null
}

export async function searchPlayersGraphql(q: string, limit = 10) {
  const response = await requestGraphQL<SearchPlayersQueryResponse>(
    `
      query SearchPlayers($q: String!, $limit: Int!, $scope: ModeScope) {
        searchPlayers(q: $q, limit: $limit) {
          count
          data {
            ${DISPLAY_PLAYER_FIELDS}
          }
        }
      }
    `,
    { q, limit },
  )

  return {
    ...response.searchPlayers,
    data: response.searchPlayers.data
      .map((player) => normalizeGraphqlPlayer(player))
      .filter((player): player is GraphqlPlayer => player !== null),
  }
}
