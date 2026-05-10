import {
  createFileRoute,
  Link,
  Outlet,
  redirect,
  useRouterState,
} from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"

const SETTINGS_TAB_OPTIONS = [
  {
    value: "profile",
    labelKey: "settings.tabs.profile",
    to: "/settings/profile",
  },
  {
    value: "social-links",
    labelKey: "settings.tabs.socialLinks",
    to: "/settings/social-links",
  },
  {
    value: "webhooks",
    labelKey: "settings.tabs.webhooks",
    to: "/settings/webhooks",
  },
  {
    value: "appearance",
    labelKey: "settings.tabs.appearance",
    to: "/settings/appearance",
  },
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
      const searchParams = new URLSearchParams(location.search)
      const requestedTab = searchParams.get("tab")
      const targetTab = SETTINGS_TAB_OPTIONS.find(
        (tab) => tab.value === requestedTab,
      )
      searchParams.delete("tab")
      const nextSearch = searchParams.toString()

      throw redirect({
        href: `${targetTab?.to ?? "/settings/profile"}${
          nextSearch ? `?${nextSearch}` : ""
        }`,
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
  const { t } = useTranslation()
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
        <h1 className="text-2xl font-bold tracking-tight">
          {t("settings.title")}
        </h1>
      </div>
      <TabsList className="w-fit border border-border bg-background/60">
        {SETTINGS_TAB_OPTIONS.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value} asChild>
            <Link to={tab.to}>{t(tab.labelKey)}</Link>
          </TabsTrigger>
        ))}
      </TabsList>
      <Outlet />
    </Tabs>
  )
}
