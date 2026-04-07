import { useState } from "react"

import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { Main } from "./Main"
import {
  getStoredSidebarLayout,
  resolveSidebarItems,
  saveSidebarLayout,
  type SidebarLayout,
} from "./sidebar-layout"
import { User } from "./User"

export function AppSidebar() {
  const { user: currentUser } = useAuth()
  const [layout, setLayout] = useState<SidebarLayout>(() => getStoredSidebarLayout())

  const items = resolveSidebarItems({
    currentUserIsSuperuser: currentUser?.is_superuser ?? false,
    profileSteamid64: currentUser?.steamid64,
    layout,
  })

  const handleLayoutChange = (nextLayout: SidebarLayout) => {
    setLayout(nextLayout)
    saveSidebarLayout(nextLayout)
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} layout={layout} onLayoutChange={handleLayoutChange} />
      </SidebarContent>
      <SidebarFooter>
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
