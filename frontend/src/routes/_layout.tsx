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
        pathname.startsWith("/dashboard") || pathname.startsWith("/profile")
          ? "max-w-[1600px]"
          : undefined
      }
    >
      <Outlet />
    </AppShell>
  )
}

export default Layout
