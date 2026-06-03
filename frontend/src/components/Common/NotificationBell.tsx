import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Bell } from "lucide-react"
import { useTranslation } from "react-i18next"

import { MeService } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import useAuth from "@/hooks/useAuth"

const UNREAD_BADGE_CAP = 99

export function NotificationBell() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const unreadCountQuery = useQuery({
    queryKey: ["me", "notifications", "unread-count"],
    queryFn: MeService.readCurrentPlayerNotificationUnreadCount,
    enabled: Boolean(user),
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })

  if (!user) {
    return null
  }

  const unreadCount = unreadCountQuery.data?.unread_count ?? 0
  const badgeLabel =
    unreadCount > UNREAD_BADGE_CAP
      ? `${UNREAD_BADGE_CAP}+`
      : String(unreadCount)

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          asChild
          variant="ghost"
          size="icon"
          className="relative text-muted-foreground"
          aria-label={t("notifications.open")}
        >
          <Link to="/notifications">
            <Bell />
            {unreadCount > 0 ? (
              <span className="-right-1 -top-1 absolute flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground leading-none">
                {badgeLabel}
              </span>
            ) : null}
          </Link>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{t("notifications.title")}</TooltipContent>
    </Tooltip>
  )
}
