import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface PointsBadgeProps {
  points: number
  className?: string
}

function getPointsToneClassName(points: number) {
  if (points === 0) {
    return "bg-muted text-foreground/80 ring-1 ring-border"
  }

  if (points >= 1000) {
    return "bg-amber-100 text-yellow-700 ring-1 ring-yellow-300"
  }

  if (points >= 900) {
    return "bg-red-100 text-red-700 ring-1 ring-red-300"
  }

  if (points >= 800) {
    return "bg-orange-100 text-amber-800 ring-1 ring-amber-300"
  }

  return "bg-slate-100 text-slate-600 ring-1 ring-slate-300"
}

export function PointsBadge({ points, className }: PointsBadgeProps) {
  return (
    <Badge
      className={cn(
        "min-w-14 justify-center border-transparent px-2.5 font-mono font-semibold tabular-nums",
        getPointsToneClassName(points),
        className,
      )}
    >
      {points}
    </Badge>
  )
}
