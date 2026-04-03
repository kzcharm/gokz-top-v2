import { queryOptions } from "@tanstack/react-query"

import {
  type MapPublic,
  MapsService,
  type PlayerPublic,
  PlayersService,
  type RecordPublic,
} from "@/client"
import { getProfilePbRecordsQueryOptions } from "@/components/Records/pb-records-utils"
import { getTierColor, normalizeTierValue } from "@/components/Servers/tier"
import type { AppScope } from "@/components/scope-provider"

export type ProfileTab = "home" | "records" | "stats"

export const PROFILE_QUERY_LIMIT = 10_000

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
}

type ProfileCompletionCard = {
  completed: number
  total: number
  tiers: ProfileCompletionTier[]
}

export type ProfileCompletionData = {
  nub: ProfileCompletionCard
  pro: ProfileCompletionCard
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
  }))
  const tierByMapId = new Map<number, number>()

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

export function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value)
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
