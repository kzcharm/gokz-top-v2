import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

import { formatTierLabel, getTierColor, normalizeTierValue } from "./tier"

interface TierBadgeProps {
  tier: number | null | undefined
  className?: string
  hideWhenUnknown?: boolean
}

export function TierBadge({
  tier,
  className,
  hideWhenUnknown = false,
}: TierBadgeProps) {
  const normalizedTier = normalizeTierValue(tier)
  const tierColor = getTierColor(tier)

  if (hideWhenUnknown && normalizedTier === null) {
    return null
  }

  return (
    <Badge
      className={cn(
        "font-semibold",
        normalizedTier === null
          ? "border-border bg-muted text-muted-foreground"
          : "border-transparent text-white",
        className,
      )}
      style={tierColor ? { backgroundColor: tierColor } : undefined}
    >
      {formatTierLabel(normalizedTier)}
    </Badge>
  )
}
