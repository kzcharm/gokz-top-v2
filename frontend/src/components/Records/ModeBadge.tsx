import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { getRecordModeOption } from "./mode"

interface ModeBadgeProps {
  mode: string
  className?: string
}

function getModeBadgeStyle(mode: string) {
  const option = getRecordModeOption(mode)

  if (option) {
    return {
      label: option.label,
      className: option.textClassName,
      style: option.style,
    }
  }

  return {
    label: mode,
    className: "border-border bg-muted text-muted-foreground",
    style: undefined,
  }
}

export function ModeBadge({ mode, className }: ModeBadgeProps) {
  const { label, className: toneClassName, style } = getModeBadgeStyle(mode)

  return (
    <Badge
      className={cn(
        "min-w-11 justify-center rounded-md border-transparent px-2 py-0.5 font-semibold tracking-[0.08em]",
        toneClassName,
        className,
      )}
      style={style}
    >
      {label}
    </Badge>
  )
}
