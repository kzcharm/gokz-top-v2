export const TIER_COLORS = {
  t0: "#6B7280",
  t1: "#47AA67",
  t2: "#3B876D",
  t3: "#F39C12",
  t4: "#FD7E15",
  t5: "#E84C3D",
  t6: "#A62010",
  t7: "#8B1099",
  t8: "#B83280",
} as const

export function normalizeTierValue(tier: number | null | undefined) {
  if (tier === null || tier === undefined || Number.isNaN(tier)) {
    return null
  }

  return Math.min(Math.max(Math.trunc(tier), 0), 8)
}

export function getTierColor(tier: number | null | undefined) {
  const normalizedTier = normalizeTierValue(tier)

  return normalizedTier === null
    ? undefined
    : TIER_COLORS[`t${normalizedTier}` as keyof typeof TIER_COLORS]
}

export function formatTierLabel(tier: number | null | undefined) {
  const normalizedTier = normalizeTierValue(tier)
  return normalizedTier === null ? "Unknown" : `T${normalizedTier}`
}
