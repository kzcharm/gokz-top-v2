import { queryOptions } from "@tanstack/react-query"

import {
  type MapPublic,
  MapsService,
  type PlayerFollowSummaryPublic,
  type PlayerPublic,
  type PlayersPublic,
  PlayersService,
  type RecordPublic,
} from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { getProfilePbRecordsQueryOptions } from "@/components/Records/pb-records-utils"
import { getTierColor, normalizeTierValue } from "@/components/Servers/tier"
import type { AppScope } from "@/components/scope-provider"

export type ProfileTab = "home" | "records" | "stats"

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

export type ProfileBan = {
  id: number
  ban_type: string
  created_on: string
  expires_on?: string | null
  notes?: string | null
}

export type ProfileBansResult = {
  count: number
  data: ProfileBan[]
}

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

export function getProfileFollowSummaryQueryOptions(identifier: string) {
  return queryOptions({
    queryKey: ["profile-follow-summary", identifier],
    queryFn: () =>
      PlayersService.readPlayerFollowSummary({
        identifier,
      }),
    retry: false,
    staleTime: 30_000,
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
  return await PlayersService.readPlayerFollowers({
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
  return await PlayersService.readPlayerFollowing({
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
    if (record.points >= 900) {
      silver += 1
    }
    if (record.points >= 800) {
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

export function formatCompactPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

export function formatRatingBadge(value: number) {
  return (value / 1158).toFixed(2)
}

export function getAvatarUrl(player: PlayerPublic) {
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
