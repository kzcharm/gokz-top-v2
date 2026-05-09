import { Link } from "@tanstack/react-router"
import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

import type { ProfileTab } from "./profile-utils"

const tabDefinitions: Array<{
  key: ProfileTab
  labelKey: string
  to:
    | "/profile/$identifier"
    | "/profile/$identifier/records"
    | "/profile/$identifier/unfinished"
    | "/profile/$identifier/stats"
}> = [
  { key: "home", labelKey: "profile.tabs.home", to: "/profile/$identifier" },
  {
    key: "records",
    labelKey: "profile.tabs.records",
    to: "/profile/$identifier/records",
  },
  {
    key: "unfinished",
    labelKey: "profile.tabs.unfinished",
    to: "/profile/$identifier/unfinished",
  },
  {
    key: "stats",
    labelKey: "profile.tabs.stats",
    to: "/profile/$identifier/stats",
  },
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
  const { t } = useTranslation()

  return (
    <Tabs value={activeTab} className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <TabsList className="w-full justify-start overflow-x-auto border border-border bg-background/60 sm:w-fit">
          {tabDefinitions.map((tab) => (
            <TabsTrigger key={tab.key} value={tab.key} asChild>
              <Link to={tab.to} params={{ identifier }}>
                {t(tab.labelKey)}
              </Link>
            </TabsTrigger>
          ))}
        </TabsList>
        {trailingContent ? (
          <div className="flex justify-start sm:justify-end">
            {trailingContent}
          </div>
        ) : null}
      </div>
    </Tabs>
  )
}
