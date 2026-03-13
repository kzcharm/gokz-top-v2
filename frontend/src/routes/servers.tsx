import { createFileRoute, Outlet, useRouterState } from "@tanstack/react-router"

import { AppShell } from "@/components/Common/AppShell"
import { ServerBrowser } from "@/components/Servers/ServerBrowser"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/servers")({
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
  const initialSearchString = useRouterState({
    select: (state) => state.location.searchStr,
  })

  return (
    <AppShell contentClassName="max-w-[1600px]">
      <ServerBrowser initialSearchString={initialSearchString} />
      <Outlet />
    </AppShell>
  )
}
