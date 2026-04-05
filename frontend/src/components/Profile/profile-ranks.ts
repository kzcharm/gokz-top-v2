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

function getLegacyThresholds(scope: AppScope) {
  switch (scope) {
    case "VNL":
      return LEGACY_RANK_THRESHOLDS.VNL
    case "SKZ":
      return LEGACY_RANK_THRESHOLDS.SKZ
    case "OVR":
    case "KZT":
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
