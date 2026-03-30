import { createFileRoute, redirect } from "@tanstack/react-router"

import AppearanceSettings from "@/components/UserSettings/AppearanceSettings"
import UserInformation from "@/components/UserSettings/UserInformation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"

const tabsConfig = [
  { value: "my-profile", title: "My profile", component: UserInformation },
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

      <Tabs defaultValue="my-profile">
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
