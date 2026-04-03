import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import ErrorComponent from "@/components/Common/ErrorComponent"
import NotFound from "@/components/Common/NotFound"
import { useScope } from "@/components/scope-provider"
import { Skeleton } from "@/components/ui/skeleton"
import { useEffect, useMemo } from "react"

import { ProfileHomeContent } from "./ProfileHomeContent"
import { ProfilePlaceholderPanel } from "./ProfilePlaceholderPanel"
import { ProfileRecordsTab } from "./ProfileRecordsTab"
import { ProfileSidebar } from "./ProfileSidebar"
import { ProfileTabs } from "./ProfileTabs"
import {
  buildProfileCompletionData,
  fetchProfilePlayer,
  getProfilePbRecordsQueryOptions,
  getProfileValidatedMapsQueryOptions,
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
  identifier,
  activeTab,
}: {
  identifier: string
  activeTab: ProfileTab
}) {
  const navigate = useNavigate()
  const { scope } = useScope()
  const playerQuery = useQuery({
    queryKey: ["profile-player", identifier],
    queryFn: () => fetchProfilePlayer(identifier),
    retry: false,
  })
  const mapsQuery = useQuery(getProfileValidatedMapsQueryOptions())
  const canonicalIdentifier =
    playerQuery.data?.custom_id || playerQuery.data?.steamid64 || null
  const playerSteamid64 = playerQuery.data?.steamid64 ?? null
  const nubRecordsQuery = useQuery({
    ...getProfilePbRecordsQueryOptions({
      steamid64: playerSteamid64,
      scope,
      isProOnly: false,
    }),
    enabled: playerSteamid64 !== null,
  })
  const proRecordsQuery = useQuery({
    ...getProfilePbRecordsQueryOptions({
      steamid64: playerSteamid64,
      scope,
      isProOnly: true,
    }),
    enabled: playerSteamid64 !== null,
  })
  const usesSidebarLayout = activeTab === "home" || activeTab === "records"
  const activeTabRoute =
    activeTab === "records"
      ? "/profile/$steamid64/records"
      : activeTab === "stats"
        ? "/profile/$steamid64/stats"
        : "/profile/$steamid64"

  useEffect(() => {
    if (!canonicalIdentifier || identifier === canonicalIdentifier) {
      return
    }

    void navigate({
      to: activeTabRoute,
      params: { steamid64: canonicalIdentifier },
      replace: true,
    })
  }, [activeTabRoute, canonicalIdentifier, identifier, navigate])

  const completion = useMemo(() => {
    return buildProfileCompletionData({
      maps: mapsQuery.data ?? [],
      nubRecords: nubRecordsQuery.data ?? [],
      proRecords: proRecordsQuery.data ?? [],
      scope,
    })
  }, [mapsQuery.data, nubRecordsQuery.data, proRecordsQuery.data, scope])

  const completionLoading =
    mapsQuery.isLoading || nubRecordsQuery.isLoading || proRecordsQuery.isLoading
  const completionError =
    mapsQuery.isError || nubRecordsQuery.isError || proRecordsQuery.isError

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

  if (identifier !== canonicalIdentifier) {
    return <ProfileSkeleton />
  }

  return (
    <div className="space-y-8">
      <ProfileTabs activeTab={activeTab} identifier={canonicalIdentifier} />

      {usesSidebarLayout ? (
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside>
            <ProfileSidebar player={player} />
          </aside>

          <section className="space-y-6">
            {activeTab === "home" ? (
              <ProfileHomeContent
                completion={completion}
                completionLoading={completionLoading}
                completionError={completionError}
              />
            ) : (
              <ProfileRecordsTab steamid64={player.steamid64} />
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
