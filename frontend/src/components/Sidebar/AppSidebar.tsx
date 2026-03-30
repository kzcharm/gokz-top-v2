import {
  Briefcase,
  Home,
  Server,
  Settings,
  User as UserIcon,
  Users,
} from "lucide-react"

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

const publicItems: Item[] = [
  { type: "link", icon: Home, title: "Dashboard", path: "/" },
  { type: "link", icon: Server, title: "Servers", path: "/servers" },
]

const privateItems: Item[] = [
  { type: "link", icon: Briefcase, title: "Items", path: "/items" },
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
  ],
}

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  const items: Item[] = currentUser
    ? currentUser.is_superuser
      ? [...publicItems, ...privateItems, adminItem]
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
