import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

import { formatStageLabel } from "./utils"

interface StageBadgeProps {
  stage: number
  className?: string
  label?: string
}

export function StageBadge({ stage, className, label }: StageBadgeProps) {
  const isMain = stage === 0
  const toneClassName = isMain
    ? "bg-sky-100 text-sky-900 ring-1 ring-sky-200"
    : "bg-amber-100 text-amber-900 ring-1 ring-amber-200"

  return (
    <Badge
      className={cn(
        "border-transparent font-semibold",
        toneClassName,
        className,
      )}
    >
      {label ?? formatStageLabel(stage)}
    </Badge>
  )
}
