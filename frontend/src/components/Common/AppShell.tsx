import type { ReactNode } from "react"

import { AdminModeToggle } from "@/components/Common/AdminModeToggle"
import { Appearance } from "@/components/Common/Appearance"
import { CommunityLinks } from "@/components/Common/CommunityLinks"
import { Footer } from "@/components/Common/Footer"
import { LanguageSelector } from "@/components/Common/LanguageSelector"
import { ScopeSelector } from "@/components/Common/ScopeSelector"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { useAppSettings } from "@/hooks/useAppSettings"
import { cn } from "@/lib/utils"

interface AppShellProps {
  children: ReactNode
  mainClassName?: string
  contentClassName?: string
}

export function AppShell({
  children,
  mainClassName,
  contentClassName,
}: AppShellProps) {
  const appSettingsQuery = useAppSettings()
  const communityLinksLocation =
    appSettingsQuery.data?.community_links_location ?? "navbar"

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-2 border-b border-border/80 bg-background/78 px-4 backdrop-blur-xl supports-[backdrop-filter]:bg-background/58">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
          <div className="ml-auto flex items-center gap-2">
            {communityLinksLocation === "navbar" ? (
              <CommunityLinks location="navbar" />
            ) : null}
            <AdminModeToggle />
            <Appearance />
            <LanguageSelector />
            <ScopeSelector />
          </div>
        </header>
        <main className={cn("min-w-0 flex-1 p-6 md:p-8", mainClassName)}>
          <div
            className={cn("mx-auto w-full max-w-7xl min-w-0", contentClassName)}
          >
            {children}
          </div>
        </main>
        <Footer communityLinksLocation={communityLinksLocation} />
      </SidebarInset>
    </SidebarProvider>
  )
}
