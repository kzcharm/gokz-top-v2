import { createFileRoute, redirect } from "@tanstack/react-router"
import { useEffect, useState } from "react"

import AppearanceSettings from "@/components/UserSettings/AppearanceSettings"
import SocialLinksSettings from "@/components/UserSettings/SocialLinksSettings"
import UserInformation from "@/components/UserSettings/UserInformation"
import WebhooksSettings from "@/components/UserSettings/WebhooksSettings"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"

const tabsConfig = [
  { value: "my-profile", title: "My profile", component: UserInformation },
  {
    value: "social-links",
    title: "Social links",
    component: SocialLinksSettings,
  },
  { value: "webhooks", title: "Webhooks", component: WebhooksSettings },
  { value: "appearance", title: "Appearance", component: AppearanceSettings },
]

export const Route = createFileRoute("/_layout/settings")({
  component: UserSettings,
  beforeLoad: () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
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

function UserSettings() {
  const { user: currentUser } = useAuth()
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window === "undefined") {
      return "my-profile"
    }
    const tab = new URLSearchParams(window.location.search).get("tab")
    return tabsConfig.some((entry) => entry.value === tab)
      ? (tab ?? "my-profile")
      : "my-profile"
  })

  useEffect(() => {
    const onPopState = () => {
      const tab = new URLSearchParams(window.location.search).get("tab")
      setActiveTab(
        tabsConfig.some((entry) => entry.value === tab)
          ? (tab ?? "my-profile")
          : "my-profile",
      )
    }

    window.addEventListener("popstate", onPopState)
    return () => window.removeEventListener("popstate", onPopState)
  }, [])

  if (!currentUser) {
    return null
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">User Settings</h1>
        <p className="text-muted-foreground">
          Manage your account settings and preferences
        </p>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(nextTab) => {
          setActiveTab(nextTab)
          const url = new URL(window.location.href)
          url.searchParams.set("tab", nextTab)
          window.history.replaceState({}, "", url)
        }}
      >
        <TabsList>
          {tabsConfig.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              {tab.title}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabsConfig.map((tab) => (
          <TabsContent key={tab.value} value={tab.value}>
            <tab.component />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
