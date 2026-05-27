import { getPlayerRatingLevel } from "@/components/Common/player-rating"
import type { AppScope } from "@/components/scope-provider"

const LEGACY_RANK_THRESHOLDS = {
  VNL: [
    0, 1, 500, 1000, 2000, 5000, 10000, 20000, 30000, 40000, 60000, 70000,
    80000, 100000, 120000, 140000, 160000, 180000, 200000, 250000, 300000,
    400000, 600000,
  ],
  SKZ: [
    0, 1, 500, 1000, 2000, 5000, 10000, 20000, 30000, 40000, 60000, 70000,
    80000, 100000, 120000, 150000, 200000, 230000, 250000, 300000, 400000,
    500000, 800000,
  ],
  KZT: [
    0, 1, 500, 1000, 2000, 5000, 10000, 20000, 30000, 40000, 60000, 70000,
    80000, 100000, 120000, 150000, 200000, 230000, 250000, 400000, 600000,
    800000, 1000000,
  ],
} as const

const LEGACY_RANK_NAMES = [
  "New",
  "Beginner-",
  "Beginner",
  "Beginner+",
  "Amateur-",
  "Amateur",
  "Amateur+",
  "Casual-",
  "Casual",
  "Casual+",
  "Regular-",
  "Regular",
  "Regular+",
  "Skilled-",
  "Skilled",
  "Skilled+",
  "Expert-",
  "Expert",
  "Expert+",
  "Semipro",
  "Pro",
  "Master",
  "Legend",
] as const

const RATING_RANK_NAMES = [
  "New",
  "Beginner",
  "Amateur",
  "Casual",
  "Regular",
  "Skilled",
  "Expert",
  "Pro",
  "Master",
  "Legend",
] as const

export type RatingRankLevel = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10

export const ratingRankBadgeClasses: Record<RatingRankLevel, string> = {
  1: "border-zinc-300/70 bg-zinc-100 text-zinc-800 dark:border-zinc-500/40 dark:bg-zinc-500/15 dark:text-zinc-200",
  2: "border-border/70 bg-background/80 text-foreground",
  3: "border-blue-300/70 bg-blue-100 text-blue-900 dark:border-blue-500/40 dark:bg-blue-500/15 dark:text-blue-200",
  4: "border-lime-300/70 bg-lime-100 text-lime-900 dark:border-lime-500/40 dark:bg-lime-500/15 dark:text-lime-200",
  5: "border-green-300/70 bg-green-100 text-green-900 dark:border-green-500/40 dark:bg-green-500/15 dark:text-green-200",
  6: "border-purple-300/70 bg-purple-100 text-purple-900 dark:border-purple-500/40 dark:bg-purple-500/15 dark:text-purple-200",
  7: "border-fuchsia-300/70 bg-fuchsia-100 text-fuchsia-900 dark:border-fuchsia-500/40 dark:bg-fuchsia-500/15 dark:text-fuchsia-200",
  8: "border-rose-300/70 bg-rose-100 text-rose-900 dark:border-rose-500/40 dark:bg-rose-500/15 dark:text-rose-200",
  9: "border-red-300/70 bg-red-100 text-red-900 dark:border-red-500/40 dark:bg-red-500/15 dark:text-red-200",
  10: "border-amber-300/70 bg-amber-100 text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-200",
}

function getLegacyThresholds(scope: AppScope) {
  switch (scope) {
    case "VNL":
      return LEGACY_RANK_THRESHOLDS.VNL
    case "SKZ":
      return LEGACY_RANK_THRESHOLDS.SKZ
    default:
      return LEGACY_RANK_THRESHOLDS.KZT
  }
}

export function getPointsRankLabel(points: number, scope: AppScope) {
  if (!Number.isFinite(points) || points < 0) {
    return "Unknown"
  }

  const thresholds = getLegacyThresholds(scope)
  for (let rankIndex = thresholds.length - 1; rankIndex >= 0; rankIndex -= 1) {
    if (points >= thresholds[rankIndex]) {
      return LEGACY_RANK_NAMES[rankIndex]
    }
  }

  return LEGACY_RANK_NAMES[0]
}

export function getRatingRankLevel(
  rating: number | null | undefined,
): RatingRankLevel {
  const level = getPlayerRatingLevel(rating)

  if (level <= 1) {
    return 1
  }

  if (level >= RATING_RANK_NAMES.length) {
    return 10
  }

  return level as RatingRankLevel
}

export function getRatingRankLabel(rating: number | null | undefined) {
  return RATING_RANK_NAMES[getRatingRankLevel(rating) - 1]
}
