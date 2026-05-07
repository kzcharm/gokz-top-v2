import {
  createFileRoute,
  Link,
  Outlet,
  redirect,
  useRouterState,
} from "@tanstack/react-router"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"

const SETTINGS_TAB_OPTIONS = [
  { value: "profile", label: "Profile", to: "/settings/profile" },
  {
    value: "social-links",
    label: "Social Links",
    to: "/settings/social-links",
  },
  { value: "webhooks", label: "Webhooks", to: "/settings/webhooks" },
  { value: "appearance", label: "Appearance", to: "/settings/appearance" },
] as const

export const Route = createFileRoute("/_layout/settings")({
  component: UserSettingsLayout,
  beforeLoad: ({ location }) => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }

    if (location.pathname === "/settings") {
      const requestedTab = new URLSearchParams(location.search).get("tab")
      const targetTab = SETTINGS_TAB_OPTIONS.find(
        (tab) => tab.value === requestedTab,
      )

      throw redirect({
        to: targetTab?.to ?? "/settings/profile",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: getPageTitle(),
      },
    ],
  }),
})

function UserSettingsLayout() {
  const { user: currentUser } = useAuth()
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })

  if (!currentUser) {
    return null
  }

  const activeTab =
    SETTINGS_TAB_OPTIONS.find((tab) => pathname.startsWith(tab.to))?.value ??
    "profile"

  return (
    <Tabs value={activeTab} className="flex flex-col gap-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
      </div>
      <TabsList className="w-fit border border-border bg-background/60">
        {SETTINGS_TAB_OPTIONS.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value} asChild>
            <Link to={tab.to}>{tab.label}</Link>
          </TabsTrigger>
        ))}
      </TabsList>
      <Outlet />
    </Tabs>
  )
}
