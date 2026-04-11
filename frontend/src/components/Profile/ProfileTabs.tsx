import { Link } from "@tanstack/react-router"
import type { ReactNode } from "react"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

import type { ProfileTab } from "./profile-utils"

const tabDefinitions: Array<{
  key: ProfileTab
  label: string
  to:
    | "/profile/$identifier"
    | "/profile/$identifier/records"
    | "/profile/$identifier/stats"
}> = [
  { key: "home", label: "Home", to: "/profile/$identifier" },
  { key: "records", label: "Records", to: "/profile/$identifier/records" },
  { key: "stats", label: "Stats", to: "/profile/$identifier/stats" },
]

export function ProfileTabs({
  activeTab,
  identifier,
  trailingContent,
}: {
  activeTab: ProfileTab
  identifier: string
  trailingContent?: ReactNode
}) {
  return (
    <Tabs value={activeTab} className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <TabsList className="w-full justify-start overflow-x-auto border border-border bg-background/60 sm:w-fit">
          {tabDefinitions.map((tab) => (
            <TabsTrigger key={tab.key} value={tab.key} asChild>
              <Link to={tab.to} params={{ identifier }}>
                {tab.label}
              </Link>
            </TabsTrigger>
          ))}
        </TabsList>
        {trailingContent ? (
          <div className="flex justify-start sm:justify-end">{trailingContent}</div>
        ) : null}
      </div>
    </Tabs>
  )
}
