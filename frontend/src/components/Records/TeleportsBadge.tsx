import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface TeleportsBadgeProps {
  teleports: number
  className?: string
}

export function TeleportsBadge({ teleports, className }: TeleportsBadgeProps) {
  const hasTeleports = teleports > 0

  return (
    <Badge
      className={cn(
        "border-transparent font-semibold",
        hasTeleports ? "text-slate-950" : "text-white",
        className,
      )}
      style={{
        backgroundColor: hasTeleports ? "#f2c40f" : "#3598db",
      }}
    >
      {teleports}
    </Badge>
  )
}
