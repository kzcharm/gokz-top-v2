import { Link } from "@tanstack/react-router"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

import type { ProfileTab } from "./profile-utils"

const tabDefinitions: Array<{
  key: ProfileTab
  label: string
  to:
    | "/profile/$steamid64"
    | "/profile/$steamid64/records"
    | "/profile/$steamid64/stats"
}> = [
  { key: "home", label: "Home", to: "/profile/$steamid64" },
  { key: "records", label: "Records", to: "/profile/$steamid64/records" },
  { key: "stats", label: "Stats", to: "/profile/$steamid64/stats" },
]

export function ProfileTabs({
  activeTab,
  identifier,
}: {
  activeTab: ProfileTab
  identifier: string
}) {
  return (
    <Tabs value={activeTab} className="flex flex-col gap-4">
      <TabsList className="w-fit border border-border bg-background/60">
        {tabDefinitions.map((tab) => (
          <TabsTrigger key={tab.key} value={tab.key} asChild>
            <Link to={tab.to} params={{ steamid64: identifier }}>
              {tab.label}
            </Link>
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
