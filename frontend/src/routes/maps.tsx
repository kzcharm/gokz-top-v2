import { createFileRoute, Outlet, useRouterState } from "@tanstack/react-router"
import { useEffect } from "react"

import { AppShell } from "@/components/Common/AppShell"
import { MapsCatalog } from "@/components/Maps/MapsCatalog"
import { markMapsVisited } from "@/lib/maps-notifications"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/maps")({
  component: MapsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle(),
      },
    ],
  }),
})

function MapsRoute() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })

  useEffect(() => {
    if (pathname === "/maps") {
      markMapsVisited()
    }
  }, [pathname])

  return (
    <AppShell contentClassName="max-w-[1600px]">
      {pathname === "/maps" ? <MapsCatalog /> : <Outlet />}
    </AppShell>
  )
}
