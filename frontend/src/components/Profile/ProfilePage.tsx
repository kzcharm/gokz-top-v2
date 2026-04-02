import { useQuery } from "@tanstack/react-query"
import ErrorComponent from "@/components/Common/ErrorComponent"
import NotFound from "@/components/Common/NotFound"
import { Skeleton } from "@/components/ui/skeleton"

import { ProfileHomeContent } from "./ProfileHomeContent"
import { ProfilePlaceholderPanel } from "./ProfilePlaceholderPanel"
import { ProfileRecordsTab } from "./ProfileRecordsTab"
import { ProfileSidebar } from "./ProfileSidebar"
import { ProfileTabs } from "./ProfileTabs"
import {
  fetchProfilePlayer,
  isValidSteamid64,
  type ProfileTab,
} from "./profile-utils"

function ProfileSkeleton() {
  return (
    <div className="space-y-8">
      <Skeleton className="h-56 rounded-[28px]" />
      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Skeleton className="h-[680px] rounded-[28px]" />
        <div className="space-y-6">
          <Skeleton className="h-48 rounded-[28px]" />
          <Skeleton className="h-64 rounded-[28px]" />
          <Skeleton className="h-80 rounded-[28px]" />
        </div>
      </div>
    </div>
  )
}

export function ProfilePage({
  steamid64,
  activeTab,
}: {
  steamid64: string
  activeTab: ProfileTab
}) {
  const isValid = isValidSteamid64(steamid64)
  const playerQuery = useQuery({
    queryKey: ["profile-player", steamid64],
    queryFn: () => fetchProfilePlayer(steamid64),
    enabled: isValid,
    retry: false,
  })

  if (!isValid) {
    return <NotFound />
  }

  if (playerQuery.isLoading) {
    return <ProfileSkeleton />
  }

  if (playerQuery.isError) {
    return <ErrorComponent />
  }

  if (!playerQuery.data) {
    return <NotFound />
  }

  const player = playerQuery.data
  const usesSidebarLayout = activeTab === "home" || activeTab === "records"

  return (
    <div className="space-y-8">
      <ProfileTabs activeTab={activeTab} steamid64={steamid64} />

      {usesSidebarLayout ? (
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside>
            <ProfileSidebar player={player} />
          </aside>

          <section className="space-y-6">
            {activeTab === "home" ? (
              <ProfileHomeContent />
            ) : (
              <ProfileRecordsTab steamid64={steamid64} />
            )}
          </section>
        </div>
      ) : (
        <ProfilePlaceholderPanel
          player={player}
          activeTab={activeTab as Exclude<ProfileTab, "home">}
        />
      )}
    </div>
  )
}
