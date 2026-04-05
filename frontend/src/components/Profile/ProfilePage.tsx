import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useEffect, useMemo, useRef } from "react"
import { type PlayerPublic, PlayersService } from "@/client"
import ErrorComponent from "@/components/Common/ErrorComponent"
import NotFound from "@/components/Common/NotFound"
import { useScope } from "@/components/scope-provider"
import { Skeleton } from "@/components/ui/skeleton"
import { getSteamid64FromAccessToken } from "@/lib/auth"

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
  const queryClient = useQueryClient()
  const { scope } = useScope()
  const recordedProfileViewsRef = useRef<Set<string>>(new Set())
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
      ? "/profile/$identifier/records"
      : activeTab === "stats"
        ? "/profile/$identifier/stats"
        : "/profile/$identifier"

  useEffect(() => {
    if (!canonicalIdentifier || identifier === canonicalIdentifier) {
      return
    }

    void navigate({
      to: activeTabRoute,
      params: { identifier: canonicalIdentifier },
      replace: true,
    })
  }, [activeTabRoute, canonicalIdentifier, identifier, navigate])

  useEffect(() => {
    if (
      !canonicalIdentifier ||
      identifier !== canonicalIdentifier ||
      !playerSteamid64
    ) {
      return
    }

    const viewerSteamid64 = getSteamid64FromAccessToken(
      localStorage.getItem("access_token"),
    )
    if (!viewerSteamid64 || viewerSteamid64 === playerSteamid64) {
      return
    }

    if (recordedProfileViewsRef.current.has(playerSteamid64)) {
      return
    }
    recordedProfileViewsRef.current.add(playerSteamid64)

    void PlayersService.createPlayerView({
      identifier: playerSteamid64,
    })
      .then((response) => {
        const applyProfileViews = (current: PlayerPublic | undefined) =>
          current
            ? {
                ...current,
                profile_views:
                  response.profile_views ?? current.profile_views ?? 0,
              }
            : current

        queryClient.setQueryData<PlayerPublic>(
          ["profile-player", identifier],
          applyProfileViews,
        )
        if (canonicalIdentifier !== identifier) {
          queryClient.setQueryData<PlayerPublic>(
            ["profile-player", canonicalIdentifier],
            applyProfileViews,
          )
        }
      })
      .catch(() => {
        recordedProfileViewsRef.current.delete(playerSteamid64)
      })
  }, [canonicalIdentifier, identifier, playerSteamid64, queryClient])

  const completion = useMemo(() => {
    return buildProfileCompletionData({
      maps: mapsQuery.data ?? [],
      nubRecords: nubRecordsQuery.data ?? [],
      proRecords: proRecordsQuery.data ?? [],
      scope,
    })
  }, [mapsQuery.data, nubRecordsQuery.data, proRecordsQuery.data, scope])

  const completionLoading =
    mapsQuery.isLoading ||
    nubRecordsQuery.isLoading ||
    proRecordsQuery.isLoading
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
            <ProfileSidebar identifier={canonicalIdentifier} player={player} />
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
