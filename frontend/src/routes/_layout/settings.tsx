import { useQuery } from "@tanstack/react-query"
import {
  createFileRoute,
  Link,
  Outlet,
  redirect,
  useRouterState,
} from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { MeService } from "@/client"
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
    value: "notifications",
    labelKey: "settings.tabs.notifications",
    to: "/settings/notifications",
  },
  {
    value: "appearance",
    labelKey: "settings.tabs.appearance",
    to: "/settings/appearance",
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
  const unreadCountQuery = useQuery({
    queryKey: ["me", "notifications", "unread-count"],
    queryFn: MeService.readCurrentPlayerNotificationUnreadCount,
    enabled: Boolean(currentUser),
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })

  if (!currentUser) {
    return null
  }

  const hasUnreadNotifications = (unreadCountQuery.data?.unread_count ?? 0) > 0
  const activeTab =
    SETTINGS_TAB_OPTIONS.find((tab) => pathname.startsWith(tab.to))?.value ??
    "profile"

  return (
    <Tabs value={activeTab} className="flex flex-col gap-6">
      <TabsList className="w-fit border border-border bg-background/60">
        {SETTINGS_TAB_OPTIONS.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value} asChild>
            <Link to={tab.to}>
              <span className="flex items-center gap-2">
                <span>{t(tab.labelKey)}</span>
                {tab.value === "notifications" && hasUnreadNotifications ? (
                  <span
                    aria-hidden="true"
                    className="size-2 rounded-full bg-destructive"
                  />
                ) : null}
              </span>
            </Link>
          </TabsTrigger>
        ))}
      </TabsList>
      <Outlet />
    </Tabs>
  )
}
