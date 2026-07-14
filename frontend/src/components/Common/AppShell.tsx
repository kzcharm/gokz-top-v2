import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { FaDiscord } from "react-icons/fa"

import { AdminModeToggle } from "@/components/Common/AdminModeToggle"
import { Appearance } from "@/components/Common/Appearance"
import { Footer } from "@/components/Common/Footer"
import { LanguageSelector } from "@/components/Common/LanguageSelector"
import { ScopeSelector } from "@/components/Common/ScopeSelector"
import { Button } from "@/components/ui/button"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { COMMUNITY_LINKS } from "@/lib/community-links"
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
  const { t } = useTranslation()

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-2 border-b border-border/80 bg-background/78 px-4 backdrop-blur-xl supports-[backdrop-filter]:bg-background/58">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
          <div className="ml-auto flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  asChild
                  variant="ghost"
                  size="icon"
                  className="text-muted-foreground"
                  aria-label={t("nav.joinDiscord")}
                >
                  <a
                    href={COMMUNITY_LINKS.discord}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <FaDiscord className="size-5" />
                  </a>
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t("nav.joinDiscordHelp")}</TooltipContent>
            </Tooltip>
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
        <Footer />
      </SidebarInset>
    </SidebarProvider>
  )
}
