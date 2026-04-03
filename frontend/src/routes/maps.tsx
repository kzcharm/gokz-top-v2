import {
  createFileRoute,
  Outlet,
  useRouterState,
} from "@tanstack/react-router"

import { AppShell } from "@/components/Common/AppShell"
import { MapsCatalog } from "@/components/Maps/MapsCatalog"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/maps")({
  component: MapsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Maps"),
      },
    ],
  }),
})

function MapsRoute() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })

  return (
    <AppShell contentClassName="max-w-[1600px]">
      {pathname === "/maps" ? <MapsCatalog /> : <Outlet />}
    </AppShell>
  )
}
