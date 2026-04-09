import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface TeleportsBadgeProps {
  teleports: number
  className?: string
}

export function formatCompactCount(value: number) {
  if (value <= 0) {
    return "PRO"
  }

  if (value <= 9999) {
    return String(value)
  }

  if (value < 1_000_000) {
    return `${Math.floor(value / 1_000)}K`
  }

  if (value < 1_000_000_000) {
    return `${Math.floor(value / 1_000_000)}M`
  }

  return "999M"
}

export function TeleportsBadge({ teleports, className }: TeleportsBadgeProps) {
  const hasTeleports = teleports > 0

  return (
    <Badge
      className={cn(
        "w-12 border-transparent px-0 font-mono font-semibold tabular-nums",
        hasTeleports ? "text-slate-950" : "text-white",
        className,
      )}
      style={{
        backgroundColor: hasTeleports ? "#f2c40f" : "#3598db",
      }}
    >
      {formatCompactCount(teleports)}
    </Badge>
  )
}
