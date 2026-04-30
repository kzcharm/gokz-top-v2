import { useQuery } from "@tanstack/react-query"
import {
  Activity,
  Clock3,
  Home,
  Map as MapIcon,
  Server,
  Settings,
  ShieldAlert,
  Trophy,
  UserCircle2,
  User as UserIcon,
  Users,
} from "lucide-react"

import { AdminServersService } from "@/client"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

const privateItems: Item[] = [
  { type: "link", icon: ShieldAlert, title: "Bans", path: "/bans" },
  { type: "link", icon: Settings, title: "Settings", path: "/settings" },
]

const adminItem: Item = {
  type: "group",
  icon: Users,
  title: "Admin",
  pathPrefix: "/admin",
  children: [
    { title: "Users", path: "/admin/users", icon: Users },
    { title: "Players", path: "/admin/players", icon: UserIcon },
    {
      title: "Player Sessions",
      path: "/admin/player-sessions",
      icon: Clock3,
    },
    { title: "Maps", path: "/admin/maps", icon: MapIcon },
    { title: "Servers", path: "/admin/servers", icon: Server },
  ],
}

const serverOwnerAdminItem: Item = {
  type: "group",
  icon: Users,
  title: "Admin",
  pathPrefix: "/admin",
  children: [{ title: "Servers", path: "/admin/servers", icon: Server }],
}

export function AppSidebar() {
  const { user: currentUser } = useAuth()
  const profileSteamid64 = currentUser?.steamid64 ?? "76561198417871586"
  const serverAdminAccessQuery = useQuery({
    queryKey: ["admin-servers-access", "sidebar"],
    queryFn: () => AdminServersService.readAdminServerAccess(),
    enabled: Boolean(currentUser) && !currentUser?.is_superuser,
    retry: false,
  })

  const publicItems: Item[] = [
    { type: "link", icon: Server, title: "Servers", path: "/servers" },
    {
      type: "link",
      icon: UserCircle2,
      title: "Profile",
      path: `/profile/${profileSteamid64}`,
      activePrefixes: ["/profile"],
    },
    {
      type: "link",
      icon: Trophy,
      title: "Leaderboards",
      path: "/leaderboards",
    },
    { type: "link", icon: Home, title: "Dashboard", path: "/dashboard" },
    { type: "link", icon: MapIcon, title: "Maps", path: "/maps" },
    { type: "link", icon: Activity, title: "Live", path: "/live" },
  ]

  const items: Item[] = currentUser
    ? currentUser.is_superuser
      ? [...publicItems, ...privateItems, adminItem]
      : serverAdminAccessQuery.data
        ? [...publicItems, ...privateItems, serverOwnerAdminItem]
        : [...publicItems, ...privateItems]
    : publicItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
