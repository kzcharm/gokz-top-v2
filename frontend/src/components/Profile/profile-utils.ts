import { queryOptions } from "@tanstack/react-query"

import {
  type MapPublic,
  MapsService,
  type MapWrPublic,
  type PlayerDetailPublic,
  type PlayerFollowSummaryPublic,
  PlayerFollowsService,
  type PlayerLikesPublic,
  type PlayerProfileHistoryEntryPublic,
  type PlayerProfileHistoryPublic,
  type PlayerProfileViewsPublic,
  type PlayerPublic,
  type PlayerStatsPublic,
  type PlayerStatType,
  type PlayersPublic,
  PlayersService,
  type RecordPublic,
  RecordsService,
} from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { getProfilePbRecordsQueryOptions } from "@/components/Records/pb-records-utils"
import { getTierColor, normalizeTierValue } from "@/components/Servers/tier"
import type { AppScope } from "@/components/scope-provider"

export type ProfileTab =
  | "home"
  | "records"
  | "unfinished"
  | "stats"
  | "jumpstats"
  | "friends"

export const PROFILE_QUERY_LIMIT = 10_000
export const PROFILE_SOCIAL_PAGE_LIMIT = 20

const PROFILE_SESSION_QUERY_CONFIG = {
  staleTime: Number.POSITIVE_INFINITY,
  gcTime: Number.POSITIVE_INFINITY,
  refetchOnMount: false,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  retry: 1,
} as const

export const profileBadgeToneClasses: Record<string, string> = {
  amber:
    "border-amber-300/70 bg-amber-100 text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-200",
  emerald:
    "border-emerald-300/70 bg-emerald-100 text-emerald-900 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-200",
  orange:
    "border-orange-300/70 bg-orange-100 text-orange-900 dark:border-orange-500/40 dark:bg-orange-500/15 dark:text-orange-200",
  sky: "border-sky-300/70 bg-sky-100 text-sky-900 dark:border-sky-500/40 dark:bg-sky-500/15 dark:text-sky-200",
  stone:
    "border-stone-300/70 bg-stone-100 text-stone-900 dark:border-stone-500/40 dark:bg-stone-500/15 dark:text-stone-200",
  violet:
    "border-violet-300/70 bg-violet-100 text-violet-900 dark:border-violet-500/40 dark:bg-violet-500/15 dark:text-violet-200",
}

export async function fetchProfilePlayer(identifier: string) {
  return await PlayersService.readPlayer({
    identifier,
  })
}

export type ProfilePlayer = PlayerDetailPublic

export async function fetchProfileViews(identifier: string) {
  return await PlayersService.readPlayerViews({
    identifier,
  })
}

export async function fetchProfileLikes(identifier: string) {
  return await PlayersService.readPlayerLikes({
    identifier,
  })
}

export async function fetchProfileLikers({
  identifier,
  offset = 0,
  limit = PROFILE_SOCIAL_PAGE_LIMIT,
}: {
  identifier: string
  offset?: number
  limit?: number
}) {
  const encodedIdentifier = encodeURIComponent(identifier)
  const accessToken = localStorage.getItem("access_token")
  const response = await fetch(
    `${OpenAPI.BASE}/v1/players/${encodedIdentifier}/likes/players?offset=${offset}&limit=${limit}`,
    {
      credentials: OpenAPI.CREDENTIALS,
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    },
  )

  if (!response.ok) {
    throw new Error("Failed to fetch profile likers")
  }

  return (await response.json()) as ProfileLikersPublic
}

export type ProfileLikeResult = PlayerLikesPublic

export type ProfileLikerPublic = PlayerPublic & {
  latest_like_at: string | null
}

export type ProfileLikersPublic = {
  data: ProfileLikerPublic[]
  count: number
}

export async function createProfileLike(identifier: string) {
  return await PlayersService.createPlayerLike({
    identifier,
  })
}

export function getProfileViewsQueryOptions(identifier: string | null) {
  return queryOptions({
    queryKey: ["profile-player-views", identifier],
    queryFn: async (): Promise<PlayerProfileViewsPublic | null> => {
      if (!identifier) {
        return null
      }

      return await fetchProfileViews(identifier)
    },
    enabled: identifier !== null,
    retry: false,
    staleTime: 30_000,
  })
}

export function getProfileLikesQueryOptions(identifier: string | null) {
  return queryOptions({
    queryKey: ["profile-player-likes", identifier],
    queryFn: async (): Promise<PlayerLikesPublic | null> => {
      if (!identifier) {
        return null
      }

      return await fetchProfileLikes(identifier)
    },
    enabled: identifier !== null,
    retry: false,
    staleTime: 30_000,
  })
}

export type ProfileBan = {
  uuid: string
  id: number | null
  ban_type: string
  created_at: string
  expires_at?: string | null
  notes?: string | null
}

export type ProfileBansResult = {
  count: number
  data: ProfileBan[]
}

export type ProfileBanStatusCheckResult = {
  message: string
  cleared_ban_count: number
  remaining_active_ban_count: number
}

export type ProfileFriendsVisibility =
  | "public"
  | "private_profile"
  | "private_friends"

export type ProfileFriendSync = {
  visibility: ProfileFriendsVisibility | null
  last_checked_at: string | null
  last_attempted_at: string | null
  next_allowed_at: string | null
  steam_friends_count: number | null
}

export type ProfileFriendsResult = {
  data: ProfilePlayer[]
  count: number
  sync: ProfileFriendSync
}

export type ProfileCommentAuthor = {
  steamid64: string
  display_name: string
}

export type ProfileComment = {
  id: string
  text: string
  created_at: string
  updated_at: string
  author: ProfileCommentAuthor
}

export type ProfileCommentsResult = {
  data: ProfileComment[]
  count: number
}

export type ProfileHistoryEntry = PlayerProfileHistoryEntryPublic
export type ProfileHistoryResult = PlayerProfileHistoryPublic

export function getProfileActiveBanQueryOptions(steamid64: string | null) {
  return queryOptions({
    queryKey: ["profile-active-bans", steamid64],
    queryFn: async () => {
      if (!steamid64) {
        return {
          count: 0,
          data: [],
        } satisfies ProfileBansResult
      }

      const params = new URLSearchParams({
        steamid64,
        is_expired: "false",
        offset: "0",
        limit: "50",
      })
      const response = await fetch(
        `${OpenAPI.BASE}/v1/bans?${params.toString()}`,
      )
      if (!response.ok) {
        throw new Error("Failed to load profile bans")
      }

      const payload = (await response.json()) as ProfileBansResult
      return {
        count: payload.count ?? 0,
        data: payload.data ?? [],
      } satisfies ProfileBansResult
    },
    enabled: steamid64 !== null,
    retry: false,
    staleTime: 30_000,
  })
}

export async function checkProfileUnbanStatus({
  identifier,
}: {
  identifier: string
}): Promise<ProfileBanStatusCheckResult> {
  const accessToken = localStorage.getItem("access_token")
  void identifier
  const response = await fetch(`${OpenAPI.BASE}/v1/me/ban-status-checks`, {
    method: "POST",
    credentials: OpenAPI.CREDENTIALS,
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  })

  const payload = (await response.json().catch(() => null)) as
    | ProfileBanStatusCheckResult
    | { detail?: string }
    | null
  if (!response.ok) {
    throw new Error(
      payload && typeof payload === "object" && "detail" in payload
        ? (payload.detail ?? "Failed to check ban status")
        : "Failed to check ban status",
    )
  }

  const result =
    payload &&
    typeof payload === "object" &&
    "message" in payload &&
    "cleared_ban_count" in payload &&
    "remaining_active_ban_count" in payload
      ? payload
      : null

  return {
    message: result?.message ?? "Ban status checked.",
    cleared_ban_count: result?.cleared_ban_count ?? 0,
    remaining_active_ban_count: result?.remaining_active_ban_count ?? 0,
  }
}

export function getProfileFollowSummaryQueryOptions(identifier: string) {
  return queryOptions({
    queryKey: ["profile-follow-summary", identifier],
    queryFn: () =>
      PlayerFollowsService.readPlayerFollowSummary({
        identifier,
      }),
    retry: false,
    staleTime: 30_000,
  })
}

export function getProfileFriendsQueryOptions(identifier: string | null) {
  return queryOptions({
    queryKey: ["profile-friends", identifier],
    queryFn: async (): Promise<ProfileFriendsResult | null> => {
      if (!identifier) {
        return null
      }

      const response = await fetch(
        `${OpenAPI.BASE}/v1/players/${encodeURIComponent(identifier)}/friends`,
      )
      if (!response.ok) {
        throw new Error("Failed to load friends")
      }
      return (await response.json()) as ProfileFriendsResult
    },
    enabled: identifier !== null,
    retry: false,
    staleTime: 30_000,
  })
}

export function getProfileCommentsQueryOptions({
  identifier,
  offset = 0,
  limit = PROFILE_SOCIAL_PAGE_LIMIT,
}: {
  identifier: string | null
  offset?: number
  limit?: number
}) {
  return queryOptions({
    queryKey: ["profile-comments", identifier, offset, limit],
    queryFn: async (): Promise<ProfileCommentsResult | null> => {
      if (!identifier) {
        return null
      }

      const params = new URLSearchParams({
        offset: `${offset}`,
        limit: `${limit}`,
      })
      const response = await fetch(
        `${OpenAPI.BASE}/v1/players/${encodeURIComponent(identifier)}/comments?${params.toString()}`,
      )
      if (!response.ok) {
        throw new Error("Failed to load comments")
      }
      return (await response.json()) as ProfileCommentsResult
    },
    enabled: identifier !== null,
    retry: false,
    staleTime: 30_000,
  })
}

export async function createProfileComment({
  identifier,
  text,
}: {
  identifier: string
  text: string
}): Promise<ProfileComment> {
  const accessToken = localStorage.getItem("access_token")
  const response = await fetch(
    `${OpenAPI.BASE}/v1/players/${encodeURIComponent(identifier)}/comments`,
    {
      method: "POST",
      credentials: OpenAPI.CREDENTIALS,
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify({ text }),
    },
  )
  const payload = (await response.json().catch(() => null)) as
    | ProfileComment
    | { detail?: string }
    | null
  if (!response.ok) {
    throw new Error(
      payload && typeof payload === "object" && "detail" in payload
        ? (payload.detail ?? "Failed to submit comment")
        : "Failed to submit comment",
    )
  }
  if (!payload || typeof payload !== "object" || !("id" in payload)) {
    throw new Error("Failed to submit comment")
  }
  return payload as ProfileComment
}

export async function deleteProfileComment({
  identifier,
  commentId,
}: {
  identifier: string
  commentId: string
}): Promise<void> {
  const accessToken = localStorage.getItem("access_token")
  const response = await fetch(
    `${OpenAPI.BASE}/v1/players/${encodeURIComponent(identifier)}/comments/${commentId}`,
    {
      method: "DELETE",
      credentials: OpenAPI.CREDENTIALS,
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    },
  )
  const payload = (await response.json().catch(() => null)) as {
    message?: string
    detail?: string
  } | null
  if (!response.ok) {
    throw new Error(payload?.detail ?? "Failed to delete comment")
  }
}

export async function syncProfileFriends({
  identifier,
}: {
  identifier: string
}): Promise<ProfileFriendsResult> {
  void identifier
  const accessToken = localStorage.getItem("access_token")
  const response = await fetch(`${OpenAPI.BASE}/v1/me/friend-sync-requests`, {
    method: "POST",
    credentials: OpenAPI.CREDENTIALS,
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  })
  const payload = (await response.json().catch(() => null)) as
    | ProfileFriendsResult
    | { detail?: string }
    | null
  if (!response.ok) {
    throw new Error(
      payload && typeof payload === "object" && "detail" in payload
        ? (payload.detail ?? "Failed to sync friends")
        : "Failed to sync friends",
    )
  }

  if (!payload || typeof payload !== "object" || !("data" in payload)) {
    throw new Error("Failed to sync friends")
  }
  return payload as ProfileFriendsResult
}

export async function fetchProfileHistory({
  identifier,
  offset = 0,
  limit = 100,
}: {
  identifier: string
  offset?: number
  limit?: number
}): Promise<ProfileHistoryResult> {
  return await PlayersService.readPlayerProfileHistory({
    identifier,
    offset,
    limit,
  })
}

export function getProfileStatsQueryOptions(
  identifier: string | null,
  type: PlayerStatType | null = null,
) {
  return queryOptions({
    queryKey: ["profile-stats", identifier, type],
    queryFn: async (): Promise<PlayerStatsPublic | null> => {
      if (!identifier) {
        return null
      }

      return await PlayersService.readPlayerStats({
        identifier,
        type,
      })
    },
    enabled: identifier !== null,
    retry: false,
    staleTime: 60_000,
  })
}

export async function fetchProfileFollowers({
  identifier,
  offset,
  limit = PROFILE_SOCIAL_PAGE_LIMIT,
}: {
  identifier: string
  offset: number
  limit?: number
}): Promise<PlayersPublic> {
  return await PlayerFollowsService.readPlayerFollowers({
    identifier,
    offset,
    limit,
  })
}

export async function fetchProfileFollowing({
  identifier,
  offset,
  limit = PROFILE_SOCIAL_PAGE_LIMIT,
}: {
  identifier: string
  offset: number
  limit?: number
}): Promise<PlayersPublic> {
  return await PlayerFollowsService.readPlayerFollowing({
    identifier,
    offset,
    limit,
  })
}

export function getProfileValidatedMapsQueryOptions() {
  return queryOptions({
    queryKey: ["maps", "validated"],
    queryFn: () =>
      MapsService.readMaps({
        offset: 0,
        limit: PROFILE_QUERY_LIMIT,
        isValidated: true,
      }),
    ...PROFILE_SESSION_QUERY_CONFIG,
  })
}

export function getProfileUnfinishedMapWrsQueryOptions({
  scope,
  isProOnly,
}: {
  scope: AppScope
  isProOnly: boolean
}) {
  return queryOptions({
    queryKey: ["profile-unfinished-wrs", scope, isProOnly],
    queryFn: () =>
      MapsService.readMapWrs({
        scope,
        type: isProOnly ? "PRO" : "NUB",
      }),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  })
}

export { getProfilePbRecordsQueryOptions }

type ProfileCompletionTier = {
  label: string
  complete: number
  total: number
  color: string
  averagePoints: number
}

type ProfileCompletionCard = {
  completed: number
  total: number
  tiers: ProfileCompletionTier[]
}

export type ProfileTrophyCounts = {
  gold: number
  silver: number
  bronze: number
}

export type ProfileCompletionData = {
  nub: ProfileCompletionCard
  pro: ProfileCompletionCard
}

export type ProfileSummaryData = {
  totalPoints: number
  rankLabel: string
  globalStanding: number | null
  regionalStanding: number | null
  region: string | null
  rating: number | null
}

export type ProfilePinnedRecord = {
  id: string
  playerSteamid64: string
  mapId: number
  scope: AppScope
  type: "NUB" | "PRO"
  record: RecordPublic
  rank: number | null
  totalCount: number | null
}

export type ProfilePinnedRecordEntry = {
  id: string
  playerSteamid64: string
  mapId: number
  scope: AppScope
  type: "NUB" | "PRO"
  record: RecordPublic
}

export type ProfileUnfinishedRow = {
  mapId: number
  mapName: string
  tier: number
  wrTime: number | null
  wrRecordUuid: string | null
}

function buildCompletionCard({
  maps,
  records,
  scope,
}: {
  maps: MapPublic[]
  records: RecordPublic[]
  scope: AppScope
}): ProfileCompletionCard {
  const tiers = Array.from({ length: 8 }, (_, index) => ({
    label: `T${index + 1}`,
    complete: 0,
    total: 0,
    color: getTierColor(index + 1) ?? "#6B7280",
    averagePoints: 0,
  }))
  const tierByMapId = new Map<number, number>()
  const tierPointsTotals = Array.from({ length: 8 }, () => 0)

  for (const map of maps) {
    const tier = normalizeTierValue(map.tiers[scope])
    if (tier === null || tier === 0) {
      continue
    }

    tiers[tier - 1].total += 1
    tierByMapId.set(map.id, tier)
  }

  const completedMapIds = new Set(records.map((record) => record.map_id))
  for (const mapId of completedMapIds) {
    const tier = tierByMapId.get(mapId)
    if (!tier) {
      continue
    }

    tiers[tier - 1].complete += 1
  }

  for (const record of records) {
    const tier = tierByMapId.get(record.map_id)
    if (!tier) {
      continue
    }

    tierPointsTotals[tier - 1] += record.points
  }

  tiers.forEach((tier, index) => {
    tier.averagePoints =
      tier.complete === 0
        ? 0
        : Math.round(tierPointsTotals[index] / tier.complete)
  })

  return {
    completed: tiers.reduce((sum, tier) => sum + tier.complete, 0),
    total: tiers.reduce((sum, tier) => sum + tier.total, 0),
    tiers,
  }
}

export function buildProfileCompletionData({
  maps,
  nubRecords,
  proRecords,
  scope,
}: {
  maps: MapPublic[]
  nubRecords: RecordPublic[]
  proRecords: RecordPublic[]
  scope: AppScope
}): ProfileCompletionData {
  return {
    nub: buildCompletionCard({ maps, records: nubRecords, scope }),
    pro: buildCompletionCard({ maps, records: proRecords, scope }),
  }
}

export function buildProfileUnfinishedRows({
  maps,
  records,
  wrs,
  scope,
}: {
  maps: MapPublic[]
  records: RecordPublic[]
  wrs: MapWrPublic[]
  scope: AppScope
}): ProfileUnfinishedRow[] {
  const completedMapIds = new Set(records.map((record) => record.map_id))
  const wrByMapId = new Map<number, MapWrPublic>()

  for (const wr of wrs) {
    if (!wrByMapId.has(wr.map_id)) {
      wrByMapId.set(wr.map_id, wr)
    }
  }

  const rows: ProfileUnfinishedRow[] = []
  for (const map of maps) {
    const tier = normalizeTierValue(map.tiers[scope])
    if (tier === null || tier === 0 || completedMapIds.has(map.id)) {
      continue
    }

    const wr = wrByMapId.get(map.id)
    rows.push({
      mapId: map.id,
      mapName: map.name,
      tier,
      wrTime: wr?.time ?? null,
      wrRecordUuid: wr?.record_uuid ?? null,
    })
  }

  return rows
}

export function buildProfileTrophyCounts(
  records: RecordPublic[],
): ProfileTrophyCounts {
  let gold = 0
  let silver = 0
  let bronze = 0

  for (const record of records) {
    if (record.points === 1000) {
      gold += 1
    }
    if (record.points >= 900 && record.points < 1000) {
      silver += 1
    }
    if (record.points >= 800 && record.points < 900) {
      bronze += 1
    }
  }

  return {
    gold,
    silver,
    bronze,
  }
}

export function buildProfileTotalPoints({
  nubRecords,
  proRecords,
}: {
  nubRecords: RecordPublic[]
  proRecords: RecordPublic[]
}) {
  let totalPoints = 0

  for (const record of nubRecords) {
    totalPoints += record.points
  }

  for (const record of proRecords) {
    totalPoints += record.points
  }

  return totalPoints
}

export function getProfilePinnedRecordKey({
  mapId,
  type,
}: {
  mapId: number
  type: "NUB" | "PRO"
}) {
  return `${mapId}:${type}`
}

export function getProfilePinnedRecordsQueryOptions({
  identifier,
  scope,
}: {
  identifier: string | null
  scope: AppScope
}) {
  return queryOptions({
    queryKey: ["profile-pinned-records", identifier, scope],
    queryFn: async () => {
      if (!identifier) {
        return [] as ProfilePinnedRecordEntry[]
      }

      const encodedIdentifier = encodeURIComponent(identifier)
      const response = await fetch(
        `${OpenAPI.BASE}/v1/players/${encodedIdentifier}/pinned-records?scope=${scope}`,
        {
          credentials: OpenAPI.CREDENTIALS,
        },
      )
      if (!response.ok) {
        throw new Error("Failed to fetch pinned records")
      }

      const payload = (await response.json()) as {
        data?: Array<{
          id: string
          player_steamid64: string
          map_id: number
          scope: AppScope
          type: "NUB" | "PRO"
          record: RecordPublic
        }>
      }

      return (payload.data ?? []).map((entry) => ({
        id: entry.id,
        playerSteamid64: entry.player_steamid64,
        mapId: entry.map_id,
        scope: entry.scope,
        type: entry.type,
        record: entry.record,
      }))
    },
    enabled: identifier !== null,
    retry: false,
    staleTime: 30_000,
  })
}

async function fetchPinnedRecordMutation(
  url: string,
  init: RequestInit,
): Promise<void> {
  const accessToken = localStorage.getItem("access_token")
  const response = await fetch(url, {
    ...init,
    credentials: OpenAPI.CREDENTIALS,
    headers: {
      ...(init.method === "POST" ? { "Content-Type": "application/json" } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(init.headers ?? {}),
    },
  })

  if (!response.ok) {
    throw new Error("Pinned record mutation failed")
  }
}

export async function pinProfileRecord({
  identifier,
  mapId,
  scope,
  type,
}: {
  identifier: string
  mapId: number
  scope: AppScope
  type: "NUB" | "PRO"
}) {
  void identifier
  await fetchPinnedRecordMutation(`${OpenAPI.BASE}/v1/me/pinned-records`, {
    method: "POST",
    body: JSON.stringify({
      map_id: mapId,
      scope,
      type,
    }),
  })
}

export async function unpinProfileRecord({
  identifier,
  mapId,
  scope,
  type,
}: {
  identifier: string
  mapId: number
  scope: AppScope
  type: "NUB" | "PRO"
}) {
  void identifier
  await fetchPinnedRecordMutation(
    `${OpenAPI.BASE}/v1/me/pinned-records/${mapId}/${scope}/${type}`,
    {
      method: "DELETE",
    },
  )
}

export function getProfileRecordRanksQueryOptions({
  recordUuids,
  scope,
}: {
  recordUuids: string[]
  scope: AppScope
}) {
  return queryOptions({
    queryKey: ["profile-record-ranks", scope, ...recordUuids],
    queryFn: async () => {
      if (recordUuids.length === 0) {
        return new Map<
          string,
          { rank: number | null; totalCount: number | null }
        >()
      }
      const data = (await RecordsService.readRecordRanks({
        uuidList: recordUuids,
        scope,
        type: "NUB",
      })) as unknown as {
        data?: Array<{
          record_uuid: string
          rank?: number | null
          total_count?: number | null
        }>
      }

      return new Map(
        (data.data ?? []).map((entry) => [
          entry.record_uuid,
          {
            rank: entry.rank ?? null,
            totalCount: entry.total_count ?? null,
          },
        ]),
      )
    },
    enabled: recordUuids.length > 0,
    ...PROFILE_SESSION_QUERY_CONFIG,
  })
}

export function getProfilePointsStandingQueryOptions({
  identifier,
  scope,
}: {
  identifier: string | null
  scope: AppScope
}) {
  return queryOptions({
    queryKey: ["profile-points-standing", identifier, scope],
    queryFn: async () => {
      if (!identifier) {
        return null
      }

      const encodedIdentifier = encodeURIComponent(identifier)
      const response = await fetch(
        `${OpenAPI.BASE}/v1/leaderboards/players/${encodedIdentifier}?scope=${scope}`,
        {
          credentials: OpenAPI.CREDENTIALS,
        },
      )

      if (!response.ok) {
        throw new Error("Failed to fetch player leaderboard rank")
      }

      const data = (await response.json()) as {
        rank?: number | null
        rank_regional?: number | null
        region?: string | null
        rating?: number | null
      }
      return {
        rank: data.rank ?? null,
        regionalRank: data.rank_regional ?? null,
        region: data.region ?? null,
        rating: data.rating ?? null,
      }
    },
    enabled: identifier !== null,
    ...PROFILE_SESSION_QUERY_CONFIG,
  })
}

export function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value)
}

export function formatRating(value: number) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatHours(hours: number) {
  return `${formatNumber(hours)} hrs`
}

export function formatSecondsAsHours(totalSeconds: number) {
  return `${(totalSeconds / 3600).toFixed(1)} hours`
}

export function formatCompactPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

export function formatRatingBadge(value: number) {
  return (value / 1158).toFixed(2)
}

export function getAvatarUrl(player: ProfilePlayer) {
  if (!player.avatar_hash) {
    return null
  }

  return `https://avatars.steamstatic.com/${player.avatar_hash}_full.jpg`
}

export function getFollowSummaryCount(
  summary: PlayerFollowSummaryPublic | undefined,
  key: "follower_count" | "following_count",
) {
  return summary?.[key] ?? 0
}
