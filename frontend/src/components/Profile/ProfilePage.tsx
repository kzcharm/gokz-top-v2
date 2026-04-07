import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { TriangleAlertIcon } from "lucide-react"
import { useEffect, useMemo, useRef } from "react"
import { type PlayerPublic, PlayersService } from "@/client"
import ErrorComponent from "@/components/Common/ErrorComponent"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import NotFound from "@/components/Common/NotFound"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"
import { getSteamid64FromAccessToken } from "@/lib/auth"
import { cn } from "@/lib/utils"

import { ProfileHomeContent } from "./ProfileHomeContent"
import { ProfilePlaceholderPanel } from "./ProfilePlaceholderPanel"
import { ProfileRecordsTab } from "./ProfileRecordsTab"
import { ProfileSidebar } from "./ProfileSidebar"
import { ProfileTabs } from "./ProfileTabs"
import { getPointsRankLabel } from "./profile-ranks"
import {
  buildProfileCompletionData,
  buildProfileTotalPoints,
  buildProfileTrophyCounts,
  fetchProfilePlayer,
  getProfileActiveBanQueryOptions,
  getProfilePbRecordsQueryOptions,
  getProfilePointsStandingQueryOptions,
  getProfileValidatedMapsQueryOptions,
  type ProfileTab,
} from "./profile-utils"

function formatBanType(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

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
  const activeBanCountQuery = useQuery(
    getProfileActiveBanQueryOptions(playerSteamid64),
  )
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
  const pointsStandingQuery = useQuery({
    ...getProfilePointsStandingQueryOptions({
      identifier: canonicalIdentifier,
      scope,
    }),
    enabled: canonicalIdentifier !== null,
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
  const summary = useMemo(() => {
    const totalPoints = buildProfileTotalPoints({
      nubRecords: nubRecordsQuery.data ?? [],
      proRecords: proRecordsQuery.data ?? [],
    })

    return {
      totalPoints,
      rankLabel: getPointsRankLabel(totalPoints, scope),
      globalStanding: pointsStandingQuery.data?.rank ?? null,
      regionalStanding: pointsStandingQuery.data?.regionalRank ?? null,
      region: pointsStandingQuery.data?.region ?? null,
      rating: pointsStandingQuery.data?.rating ?? null,
    }
  }, [
    nubRecordsQuery.data,
    pointsStandingQuery.data,
    proRecordsQuery.data,
    scope,
  ])
  const completionTrophies = useMemo(() => {
    return {
      nub: buildProfileTrophyCounts(nubRecordsQuery.data ?? []),
      pro: buildProfileTrophyCounts(proRecordsQuery.data ?? []),
    }
  }, [nubRecordsQuery.data, proRecordsQuery.data])

  const completionLoading =
    mapsQuery.isLoading ||
    nubRecordsQuery.isLoading ||
    proRecordsQuery.isLoading
  const summaryLoading =
    nubRecordsQuery.isLoading ||
    proRecordsQuery.isLoading ||
    pointsStandingQuery.isLoading
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

  const activeBans = activeBanCountQuery.data?.data ?? []
  const activeBanCount = activeBanCountQuery.data?.count ?? 0
  const hasPermanentBan = activeBans.some((ban) => ban.expires_on == null)
  const showBanWarning = activeBanCount > 0

  return (
    <div className="space-y-8">
      <ProfileTabs activeTab={activeTab} identifier={canonicalIdentifier} />

      {showBanWarning ? (
        <Alert
          variant={hasPermanentBan ? "destructive" : "default"}
          className={cn(
            "gap-y-3",
            hasPermanentBan
              ? "border-destructive/40 bg-destructive/10 text-destructive"
              : "border-amber-300/70 bg-amber-50 text-amber-950 [&>svg]:text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100 dark:[&>svg]:text-amber-300",
          )}
        >
          <TriangleAlertIcon />
          <AlertTitle>This player has been banned</AlertTitle>
          <AlertDescription
            className={cn(
              "gap-3",
              hasPermanentBan
                ? "text-destructive/90"
                : "text-amber-800 dark:text-amber-200",
            )}
          >
            <div className="grid gap-3">
              {activeBans.map((ban) => (
                <div
                  key={ban.id}
                  className={cn(
                    "rounded-xl border px-4 py-3",
                    hasPermanentBan
                      ? "border-destructive/30 bg-background/70"
                      : "border-amber-300/50 bg-background/70 dark:border-amber-500/20",
                  )}
                >
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-medium">
                    <span>{formatBanType(ban.ban_type)}</span>
                    <span className="text-muted-foreground">•</span>
                    <FormattedDateTime
                      value={ban.created_on}
                      display="absolute"
                      fallback="Unknown date"
                    />
                    <span className="text-muted-foreground">•</span>
                    <span>
                      {ban.expires_on == null ? "Permanent" : "Temporary"}
                    </span>
                  </div>
                  <p className="mt-2 text-sm">
                    {ban.notes?.trim() ? ban.notes : "No notes provided."}
                  </p>
                </div>
              ))}
            </div>
          </AlertDescription>
        </Alert>
      ) : null}

      {usesSidebarLayout ? (
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside>
            <ProfileSidebar
              identifier={canonicalIdentifier}
              player={player}
              summary={summary}
              summaryLoading={summaryLoading}
            />
          </aside>

          <section className="space-y-6">
            {activeTab === "home" ? (
              <ProfileHomeContent
                completion={completion}
                completionLoading={completionLoading}
                completionError={completionError}
                completionTrophies={completionTrophies}
                summary={summary}
                summaryLoading={summaryLoading}
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
