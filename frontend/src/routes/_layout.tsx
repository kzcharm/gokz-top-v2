import { createFileRoute, Outlet } from "@tanstack/react-router"

import { AppShell } from "@/components/Common/AppShell"

export const Route = createFileRoute("/_layout")({
  component: Layout,
})

function Layout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  )
}

export default Layout
