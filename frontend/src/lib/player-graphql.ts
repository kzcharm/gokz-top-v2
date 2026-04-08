import { requestGraphQL } from "@/lib/graphql"

export type GraphqlPlayer = {
  steamid64: string
  displayName: string
  name: string
  alias: string | null
  customId: string | null
  avatarHash: string | null
  country: string | null
  isWebsiteUser: boolean
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
  isWebsiteUser
`

export async function fetchPlayerByIdentifier(identifier: string) {
  const response = await requestGraphQL<PlayerQueryResponse>(
    `
      query PlayerByIdentifier($identifier: String!) {
        player(identifier: $identifier) {
          ${DISPLAY_PLAYER_FIELDS}
          lastPlayedAt
          createdAt
          updatedAt
          profileViews
        }
      }
    `,
    { identifier },
  )

  return response.player
}

async function requestPlayersForDisplay(steamid64s: string[]) {
  if (steamid64s.length === 0) {
    return []
  }

  const response = await requestGraphQL<PlayersQueryResponse>(
    `
      query PlayersForDisplay($steamid64s: [ID!]!) {
        players(steamid64s: $steamid64s) {
          ${DISPLAY_PLAYER_FIELDS}
          lastPlayedAt
        }
      }
    `,
    { steamid64s },
  )

  return response.players
}

let pendingPlayerBatch = new Map<string, PendingPlayerBatchEntry[]>()
let pendingPlayerBatchTimer: ReturnType<typeof setTimeout> | null = null
const cachedDisplayPlayers = new Map<string, GraphqlPlayer | null>()
const inflightDisplayPlayers = new Map<string, Promise<GraphqlPlayer | null>>()

function queuePlayerBatchLoad(steamid64: string) {
  const existingPromise = inflightDisplayPlayers.get(steamid64)
  if (existingPromise) {
    return existingPromise
  }

  const promise = new Promise<GraphqlPlayer | null>((resolve, reject) => {
    const existingResolvers = pendingPlayerBatch.get(steamid64) ?? []
    existingResolvers.push({ resolve, reject })
    pendingPlayerBatch.set(steamid64, existingResolvers)

    if (pendingPlayerBatchTimer !== null) {
      return
    }

    pendingPlayerBatchTimer = setTimeout(() => {
      void flushPendingPlayerBatch()
    }, PLAYER_BATCH_DELAY_MS)
  })

  inflightDisplayPlayers.set(steamid64, promise)
  return promise
}

async function flushPendingPlayerBatch() {
  const currentBatch = pendingPlayerBatch
  pendingPlayerBatch = new Map()
  pendingPlayerBatchTimer = null

  const steamid64s = [...currentBatch.keys()]
  try {
    const players = await requestPlayersForDisplay(steamid64s)
    steamid64s.forEach((steamid64, index) => {
      const resolvers = currentBatch.get(steamid64) ?? []
      const player = players[index] ?? null
      cachedDisplayPlayers.set(steamid64, player)
      inflightDisplayPlayers.delete(steamid64)
      for (const entry of resolvers) {
        entry.resolve(player)
      }
    })
  } catch (error) {
    for (const steamid64 of steamid64s) {
      inflightDisplayPlayers.delete(steamid64)
    }
    for (const resolvers of currentBatch.values()) {
      for (const entry of resolvers) {
        entry.reject(error)
      }
    }
  }
}

export async function fetchPlayersForDisplay(steamid64s: string[]) {
  if (steamid64s.length === 0) {
    return []
  }

  const uncachedSteamid64s = steamid64s.filter(
    (steamid64) => !cachedDisplayPlayers.has(steamid64),
  )

  await Promise.all(
    uncachedSteamid64s.map((steamid64) => queuePlayerBatchLoad(steamid64)),
  )

  return steamid64s.map((steamid64) => cachedDisplayPlayers.get(steamid64) ?? null)
}

export async function loadPlayerForDisplay(steamid64: string) {
  const [player] = await fetchPlayersForDisplay([steamid64])
  return player ?? null
}

export async function searchPlayersGraphql(q: string, limit = 10) {
  const response = await requestGraphQL<SearchPlayersQueryResponse>(
    `
      query SearchPlayers($q: String!, $limit: Int!) {
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

  return response.searchPlayers
}
