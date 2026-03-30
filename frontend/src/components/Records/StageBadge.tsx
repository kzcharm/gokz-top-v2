import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

import { formatStageLabel } from "./utils"

interface StageBadgeProps {
  stage: number
  className?: string
}

export function StageBadge({ stage, className }: StageBadgeProps) {
  const isMain = stage === 0

  return (
    <Badge
      className={cn("border-transparent font-semibold text-white", className)}
      style={{
        backgroundColor: isMain ? "#1f8f6a" : "#cf6a2c",
      }}
    >
      {formatStageLabel(stage)}
    </Badge>
  )
}
