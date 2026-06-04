import { useQuery } from "@tanstack/react-query"
import { Link as RouterLink } from "@tanstack/react-router"
import { LogIn } from "lucide-react"
import { useTranslation } from "react-i18next"

import { MeService, PlayersService } from "@/client"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { getInitials } from "@/utils"

interface UserInfoProps {
  name?: string
  steamid64?: string | number
  avatarHash?: string | null
  unreadLabel?: string
  unreadCount?: number
}

const UNREAD_BADGE_CAP = 99

function UserInfo({
  name,
  steamid64,
  avatarHash,
  unreadLabel,
  unreadCount = 0,
}: UserInfoProps) {
  const avatarSrc = avatarHash
    ? `https://avatars.steamstatic.com/${avatarHash}_full.jpg`
    : undefined
  const badgeLabel =
    unreadCount > UNREAD_BADGE_CAP
      ? `${UNREAD_BADGE_CAP}+`
      : String(unreadCount)

  return (
    <div className="flex items-center gap-2.5 w-full min-w-0">
      <span className="relative shrink-0">
        <Avatar className="size-8">
          <AvatarImage src={avatarSrc} alt={`${name || "User"} avatar`} />
          <AvatarFallback className="bg-zinc-600 text-white">
            {getInitials(name || "User")}
          </AvatarFallback>
        </Avatar>
        {unreadCount > 0 ? (
          <span className="-bottom-1 -right-1 absolute flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[9px] font-semibold text-destructive-foreground leading-none ring-2 ring-sidebar">
            <span className="sr-only">{unreadLabel}</span>
            {badgeLabel}
          </span>
        ) : null}
      </span>
      <div className="flex flex-col items-start min-w-0">
        <p className="text-sm font-medium truncate w-full">
          {name || "Unknown"}
        </p>
        <p className="text-xs text-muted-foreground truncate w-full">
          {steamid64 || "N/A"}
        </p>
      </div>
    </div>
  )
}

export function User({ user }: { user: any }) {
  const { t } = useTranslation()
  const { isMobile, setOpenMobile } = useSidebar()
  const playerQuery = useQuery({
    queryKey: ["sidebar-user-player", user?.steamid64],
    enabled: Boolean(user?.steamid64),
    queryFn: () => PlayersService.readPlayer({ identifier: user.steamid64 }),
    staleTime: 60_000,
  })
  const unreadCountQuery = useQuery({
    queryKey: ["me", "notifications", "unread-count"],
    queryFn: MeService.readCurrentPlayerNotificationUnreadCount,
    enabled: Boolean(user),
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })

  const handleMenuClick = () => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }
  if (!user) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            size="lg"
            tooltip={t("auth.login")}
            asChild
            data-testid="sidebar-login-button"
          >
            <RouterLink to="/login" onClick={handleMenuClick}>
              <LogIn />
              <span>{t("auth.login")}</span>
            </RouterLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    )
  }

  const player = playerQuery.data
  const unreadCount = unreadCountQuery.data?.unread_count ?? 0
  const hasUnreadNotifications = unreadCount > 0
  const userLinkTarget = hasUnreadNotifications
    ? "/settings/notifications"
    : "/settings/profile"

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton
          size="lg"
          tooltip={
            hasUnreadNotifications
              ? t("notifications.title")
              : t("nav.settings")
          }
          asChild
          data-testid={
            hasUnreadNotifications
              ? "sidebar-user-notifications-link"
              : "sidebar-user-settings-link"
          }
        >
          <RouterLink to={userLinkTarget} onClick={handleMenuClick}>
            <UserInfo
              name={player?.alias || player?.name || user?.player?.display_name}
              steamid64={user?.steamid64}
              avatarHash={player?.avatar_hash}
              unreadLabel={t("notifications.unreadCount", {
                count: unreadCount,
              })}
              unreadCount={unreadCount}
            />
          </RouterLink>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
