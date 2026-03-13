import type { ReactNode } from "react"

import { Appearance } from "@/components/Common/Appearance"
import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
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
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-2 border-b border-border/80 bg-background/78 px-4 backdrop-blur-xl supports-[backdrop-filter]:bg-background/58">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
          <div className="ml-auto">
            <Appearance />
          </div>
        </header>
        <main className={cn("flex-1 p-6 md:p-8", mainClassName)}>
          <div className={cn("mx-auto w-full max-w-7xl", contentClassName)}>
            {children}
          </div>
        </main>
        <Footer />
      </SidebarInset>
    </SidebarProvider>
  )
}
