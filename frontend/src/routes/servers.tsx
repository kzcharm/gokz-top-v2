import { createFileRoute, Outlet } from "@tanstack/react-router"

import { AppShell } from "@/components/Common/AppShell"
import { ServerBrowser } from "@/components/Servers/ServerBrowser"
import { normalizeServersSearch } from "@/components/Servers/utils"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/servers")({
  validateSearch: normalizeServersSearch,
  component: ServersRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Servers"),
      },
    ],
  }),
})

function ServersRoute() {
  const search = Route.useSearch()

  return (
    <AppShell contentClassName="max-w-[1600px]">
      <ServerBrowser search={search} />
      <Outlet />
    </AppShell>
  )
}
