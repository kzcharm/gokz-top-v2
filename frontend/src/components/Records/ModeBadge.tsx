import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface ModeBadgeProps {
  mode: string
  className?: string
}

function getModeBadgeStyle(mode: string) {
  switch (mode.trim().toUpperCase()) {
    case "KZT":
      return {
        label: "KZT",
        className: "border-transparent text-white",
        style: { backgroundColor: "#4a95d9" },
      }
    case "SKZ":
      return {
        label: "SKZ",
        className: "border-transparent text-white",
        style: { backgroundColor: "#4ebd78" },
      }
    case "VNL":
      return {
        label: "VNL",
        className: "border-transparent text-white",
        style: { backgroundColor: "#f69231" },
      }
    default:
      return {
        label: mode,
        className: "border-border bg-muted text-muted-foreground",
        style: undefined,
      }
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
