import {
  createFileRoute,
  Link,
  Outlet,
  redirect,
  useRouterState,
} from "@tanstack/react-router"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { getPageTitle } from "@/lib/site"

const LEADERBOARD_TAB_OPTIONS = [
  { value: "players", label: "Players", to: "/leaderboards/players" },
  { value: "pow", label: "POW", to: "/leaderboards/pow" },
  { value: "jumpstats", label: "Jumpstats", to: "/leaderboards/jumpstats" },
  { value: "servers", label: "Servers", to: "/leaderboards/servers" },
  { value: "maps", label: "Maps", to: "/leaderboards/maps" },
] as const

export const Route = createFileRoute("/_layout/leaderboards")({
  beforeLoad: ({ location }) => {
    if (location.pathname === "/leaderboards") {
      throw redirect({
        to: "/leaderboards/players",
      })
    }
  },
  component: LeaderboardsLayout,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Leaderboards"),
      },
    ],
  }),
})

function LeaderboardsLayout() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })

  const activeTab =
    LEADERBOARD_TAB_OPTIONS.find((tab) => pathname.startsWith(tab.to))?.value ??
    "players"

  return (
    <Tabs value={activeTab} className="flex flex-col gap-6">
      <TabsList className="w-fit border border-border bg-background/60">
        {LEADERBOARD_TAB_OPTIONS.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value} asChild>
            <Link to={tab.to}>{tab.label}</Link>
          </TabsTrigger>
        ))}
      </TabsList>
      <Outlet />
    </Tabs>
  )
}
