import { useTranslation } from "react-i18next"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

export function PlayerActivityBadge({
  steamid64,
  lastPlayedAt,
  isOnline = false,
  refreshedAt = 0,
  size = "default",
  testId = `player-activity-${steamid64}`,
}: {
  steamid64: string
  lastPlayedAt?: string | null
  isOnline?: boolean
  refreshedAt?: number
  size?: "compact" | "default" | "profile"
  testId?: string
}) {
  const { t } = useTranslation()
  const { formatDateTime } = useDateTimeFormat()
  const lastPlayedTime = lastPlayedAt ? Date.parse(lastPlayedAt) : Number.NaN
  const now = Math.max(Date.now(), refreshedAt)
  const activityAge = now - lastPlayedTime
  const oneYearAgo = new Date(now)
  oneYearAgo.setUTCFullYear(oneYearAgo.getUTCFullYear() - 1)
  const status = isOnline
    ? "online"
    : activityAge >= 0 && activityAge <= 7 * 24 * 60 * 60 * 1000
      ? "recent"
      : lastPlayedTime <= oneYearAgo.getTime()
        ? "older"
        : null

  if (!/^\d{17}$/.test(steamid64) || status === null) {
    return null
  }

  const label =
    status === "online"
      ? t("playerActivity.online")
      : `${status === "recent" ? `${t("playerActivity.recent")} · ` : ""}${t("playerActivity.lastPlayed", { date: formatDateTime(lastPlayedAt) })}`

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label={label}
          data-testid={testId}
          data-status={status}
          className={cn(
            "absolute rounded-full",
            size === "profile"
              ? "right-0 bottom-0 size-6 border-4 border-card"
              : "-right-0.5 -bottom-0.5 border-2 border-background",
            size === "compact" && "size-2.5",
            size === "default" && "size-3",
            status === "online" && "bg-player-online",
            status === "recent" && "bg-player-recent",
            status === "older" && "bg-muted-foreground",
          )}
        />
      </TooltipTrigger>
      <TooltipContent sideOffset={8}>{label}</TooltipContent>
    </Tooltip>
  )
}
