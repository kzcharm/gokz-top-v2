import { createFileRoute, Outlet, useRouterState } from "@tanstack/react-router"

import { AppShell } from "@/components/Common/AppShell"

export const Route = createFileRoute("/_layout")({
  component: Layout,
})

function Layout() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })

  return (
    <AppShell
      contentClassName={
        pathname.startsWith("/dashboard") ||
        pathname.startsWith("/profile") ||
        pathname.startsWith("/leaderboards") ||
        pathname.startsWith("/admin/servers") ||
        pathname.startsWith("/admin/player-sessions") ||
        pathname.startsWith("/bans") ||
        pathname.startsWith("/live") ||
        pathname.startsWith("/media") ||
        pathname.startsWith("/updates")
          ? "max-w-[1600px]"
          : undefined
      }
    >
      <Outlet />
    </AppShell>
  )
}

export default Layout
