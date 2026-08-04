import { useQuery } from "@tanstack/react-query"
import {
  Clock3,
  Home,
  Link as LinkIcon,
  Map as MapIcon,
  Radio,
  Server,
  ShieldAlert,
  Trophy,
  UserCircle2,
  User as UserIcon,
  Users,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { AdminServersService, LiveService } from "@/client"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { hasRole, isSuperuser } from "@/lib/user-roles"
import { type Item, Main } from "./Main"
import { User } from "./User"

const AXE_KZ_MINOR_SEEN_STORAGE_KEY = "gokz-axe-kz-minor-seen"

function hasSeenAxeKzMinor() {
  try {
    return localStorage.getItem(AXE_KZ_MINOR_SEEN_STORAGE_KEY) === "1"
  } catch {
    return false
  }
}

export function AppSidebar() {
  const { t } = useTranslation()
  const { user: currentUser } = useAuth()
  const [hasClickedLive, setHasClickedLive] = useState(false)
  const [hasClickedMinor, setHasClickedMinor] = useState(hasSeenAxeKzMinor)
  const profileSteamid64 = currentUser?.steamid64 ?? "76561198417871586"
  const currentUserIsSuperuser = isSuperuser(currentUser)
  const serverAdminAccessQuery = useQuery({
    queryKey: ["admin-servers-access", "sidebar"],
    queryFn: () => AdminServersService.readAdminServerAccess(),
    enabled: Boolean(currentUser) && !currentUserIsSuperuser,
    retry: false,
  })
  const liveStreamsQuery = useQuery({
    queryKey: ["live-streams", "sidebar"],
    queryFn: () => LiveService.readLiveStreams({ online: true }),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const showLiveDot =
    liveStreamsQuery.data !== undefined &&
    liveStreamsQuery.data.count >= 1 &&
    !hasClickedLive

  const publicItems: Item[] = [
    { type: "link", icon: Server, title: t("nav.servers"), path: "/servers" },
    {
      type: "link",
      icon: UserCircle2,
      title: t("nav.profile"),
      path: `/profile/${profileSteamid64}`,
      activePrefixes: ["/profile"],
    },
    {
      type: "link",
      icon: Trophy,
      title: t("nav.leaderboards"),
      path: "/leaderboards",
    },
    { type: "link", icon: Home, title: t("nav.dashboard"), path: "/dashboard" },
    { type: "link", icon: MapIcon, title: t("nav.maps"), path: "/maps" },
    {
      type: "link",
      icon: Radio,
      title: t("nav.live"),
      path: "/live",
      showNotificationDot: showLiveDot,
    },
    {
      type: "link",
      icon: Trophy,
      title: "AXE KZ Minor",
      path: "https://axekz.com/tournament/axekz-minor",
      external: true,
      showNotificationDot: !hasClickedMinor,
    },
    { type: "link", icon: ShieldAlert, title: t("nav.bans"), path: "/bans" },
  ]

  const adminChildren = currentUserIsSuperuser
    ? [
        { title: t("nav.users"), path: "/admin/users", icon: Users },
        { title: t("nav.players"), path: "/admin/players", icon: UserIcon },
        { title: "Tournaments", path: "/admin/tournaments", icon: Trophy },
        {
          title: t("nav.socialLinks"),
          path: "/admin/player-social-links",
          icon: LinkIcon,
        },
        {
          title: t("nav.playerSessions"),
          path: "/admin/player-sessions",
          icon: Clock3,
        },
        { title: t("nav.maps"), path: "/admin/maps", icon: MapIcon },
        {
          title: t("nav.servers"),
          path: "/admin/servers/globalapi-server",
          icon: Server,
        },
      ]
    : [
        ...(hasRole(currentUser, "map_admin")
          ? [{ title: t("nav.maps"), path: "/admin/maps", icon: MapIcon }]
          : []),
        ...(serverAdminAccessQuery.data
          ? [
              {
                title: t("nav.servers"),
                path: "/admin/servers/globalapi-server",
                icon: Server,
              },
            ]
          : []),
      ]

  const adminItem: Item | null =
    adminChildren.length > 0
      ? {
          type: "group",
          icon: Users,
          title: t("nav.admin"),
          pathPrefix: "/admin",
          children: adminChildren,
        }
      : null

  const items: Item[] = currentUser
    ? adminItem
      ? [...publicItems, adminItem]
      : publicItems
    : publicItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main
          items={items}
          onLinkNavigate={(path) => {
            if (path === "/live") {
              setHasClickedLive(true)
            }
            if (path === "https://axekz.com/tournament/axekz-minor") {
              try {
                localStorage.setItem(AXE_KZ_MINOR_SEEN_STORAGE_KEY, "1")
              } catch {
                // Keep the dot dismissed for this visit when storage is unavailable.
              }
              setHasClickedMinor(true)
            }
          }}
        />
      </SidebarContent>
      <SidebarFooter>
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
