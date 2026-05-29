import {
  getPlayerRatingLevel,
  getPlayerRatingBadgeIcon,
  RATING_RANK_COLORS,
  type PlayerRatingLevel,
  type RatingRankLevel,
} from "@/components/Common/player-rating"
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

export const RATING_RANK_NAMES = [
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

const RATING_RANK_MINIMUMS = [
  0, 2, 3, 4, 5, 6, 7, 8, 9, 10,
] as const

export const ratingRankBadgeClasses: Record<RatingRankLevel, string> = {
  1: "border-[#CCCCCC]/70 bg-[#CCCCCC]/20 text-zinc-800 dark:text-[#CCCCCC]",
  2: "border-[#FFFFFF]/70 bg-[#FFFFFF]/80 text-zinc-950 dark:bg-[#FFFFFF]/15 dark:text-[#FFFFFF]",
  3: "border-[#99CCFF]/70 bg-[#99CCFF]/20 text-sky-950 dark:text-[#99CCFF]",
  4: "border-[#99FF99]/70 bg-[#99FF99]/20 text-green-950 dark:text-[#99FF99]",
  5: "border-[#00FF00]/70 bg-[#00FF00]/20 text-green-950 dark:text-[#00FF00]",
  6: "border-[#CC99FF]/70 bg-[#CC99FF]/20 text-purple-950 dark:text-[#CC99FF]",
  7: "border-[#FF66CC]/70 bg-[#FF66CC]/20 text-fuchsia-950 dark:text-[#FF66CC]",
  8: "border-[#FF4040]/70 bg-[#FF4040]/20 text-red-950 dark:text-[#FF4040]",
  9: "border-[#FF0000]/70 bg-[#FF0000]/20 text-red-950 dark:text-[#FF0000]",
  10: "border-[#FFE45C]/80 bg-[linear-gradient(135deg,rgba(255,248,184,0.72),rgba(255,204,0,0.32)_42%,rgba(184,120,0,0.28))] text-yellow-950 shadow-[0_0_18px_rgba(255,204,0,0.24)] dark:text-[#FFE45C]",
}

export { RATING_RANK_COLORS }

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

export function getRatingRankMinimum(level: RatingRankLevel) {
  return RATING_RANK_MINIMUMS[level - 1]
}

export function getRatingRankLadder() {
  return RATING_RANK_NAMES.map((name, index) => {
    const level = (index + 1) as RatingRankLevel

    return {
      level,
      name,
      minimumRating: getRatingRankMinimum(level),
      color: RATING_RANK_COLORS[level],
      iconSrc: getPlayerRatingBadgeIcon(level as PlayerRatingLevel),
    }
  }).reverse()
}
