import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { TriangleAlertIcon } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { PlayersService } from "@/client"
import ErrorComponent from "@/components/Common/ErrorComponent"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import NotFound from "@/components/Common/NotFound"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { getSteamid64FromAccessToken } from "@/lib/auth"
import { cn } from "@/lib/utils"
import { extractErrorMessage } from "@/utils"
import { ProfileCommentsTab } from "./ProfileCommentsTab"
import { ProfileFriendsTab } from "./ProfileFriendsTab"
import {
  ProfileCompletionSection,
  ProfileHomeContent,
} from "./ProfileHomeContent"
import { ProfileJumpstatsTab } from "./ProfileJumpstatsTab"
import { ProfileRecordsTab } from "./ProfileRecordsTab"
import { ProfileSidebar } from "./ProfileSidebar"
import { ProfileStatsContent } from "./ProfileStatsContent"
import { ProfileTabs } from "./ProfileTabs"
import { ProfileUnfinishedTab } from "./ProfileUnfinishedTab"
import { getRatingRankLabel } from "./profile-ranks"
import { buildProfileRecordDistribution } from "./profile-record-distribution"
import {
  buildProfileCompletionData,
  buildProfileTotalPoints,
  buildProfileTrophyCounts,
  checkProfileUnbanStatus,
  createProfileLike,
  fetchProfilePlayer,
  getProfileActiveBanQueryOptions,
  getProfileFriendsQueryOptions,
  getProfileLikesQueryOptions,
  getProfilePbRecordsQueryOptions,
  getProfilePinnedRecordKey,
  getProfilePinnedRecordsQueryOptions,
  getProfilePointsStandingQueryOptions,
  getProfileRecordRanksQueryOptions,
  getProfileStatsQueryOptions,
  getProfileValidatedMapsQueryOptions,
  getProfileViewsQueryOptions,
  type ProfileLikeResult,
  type ProfileTab,
  pinProfileRecord,
  syncProfileFriends,
  unpinProfileRecord,
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
      <div className="grid min-w-0 gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
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
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { scope } = useScope()
  const { user: currentUser } = useAuth()
  const recordedProfileViewsRef = useRef<Set<string>>(new Set())
  const autoSyncedFriendsRef = useRef<Set<string>>(new Set())
  const [isProOnly, setIsProOnly] = useState(false)
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
  const profileViewsQuery = useQuery(
    getProfileViewsQueryOptions(playerSteamid64),
  )
  const profileLikesQuery = useQuery(
    getProfileLikesQueryOptions(playerSteamid64),
  )
  const playerStatsQuery = useQuery({
    ...getProfileStatsQueryOptions(
      canonicalIdentifier,
      activeTab === "records" || activeTab === "unfinished" ? "playtime" : null,
    ),
    enabled: canonicalIdentifier !== null,
  })
  const friendsQuery = useQuery({
    ...getProfileFriendsQueryOptions(canonicalIdentifier),
    enabled: canonicalIdentifier !== null && activeTab === "friends",
  })
  const nubRecordsQuery = useQuery({
    ...getProfilePbRecordsQueryOptions({
      identifier: playerSteamid64,
      scope,
      isProOnly: false,
    }),
    enabled: playerSteamid64 !== null,
  })
  const proRecordsQuery = useQuery({
    ...getProfilePbRecordsQueryOptions({
      identifier: playerSteamid64,
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
  const activeTabRoute =
    activeTab === "records"
      ? "/profile/$identifier/records"
      : activeTab === "unfinished"
        ? "/profile/$identifier/unfinished"
        : activeTab === "stats"
          ? "/profile/$identifier/stats"
          : activeTab === "jumpstats"
            ? "/profile/$identifier/jumpstats"
            : activeTab === "friends"
              ? "/profile/$identifier/friends"
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
        queryClient.setQueryData(
          ["profile-player-views", playerSteamid64],
          response,
        )
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
  const pinnedRecordsQuery = useQuery(
    getProfilePinnedRecordsQueryOptions({
      identifier: playerSteamid64,
      scope,
    }),
  )
  const pinnedRecordCandidates = pinnedRecordsQuery.data ?? []
  const pinnedRecordUuids = useMemo(
    () => pinnedRecordCandidates.map((entry) => entry.record.uuid),
    [pinnedRecordCandidates],
  )
  const pinnedRecordRanksQuery = useQuery(
    getProfileRecordRanksQueryOptions({
      recordUuids: pinnedRecordUuids,
      scope,
    }),
  )
  const pinnedRecords = useMemo(() => {
    const rankByUuid =
      pinnedRecordRanksQuery.data ??
      new Map<string, { rank: number | null; totalCount: number | null }>()
    return pinnedRecordCandidates.map((entry) => ({
      ...entry,
      rank: rankByUuid.get(entry.record.uuid)?.rank ?? null,
      totalCount: rankByUuid.get(entry.record.uuid)?.totalCount ?? null,
    }))
  }, [pinnedRecordCandidates, pinnedRecordRanksQuery.data])
  const isOwnProfile = currentUser?.steamid64 === playerSteamid64
  const pinnedRecordKeys = useMemo(() => {
    return new Set(
      pinnedRecordCandidates.map((entry) =>
        getProfilePinnedRecordKey({ mapId: entry.mapId, type: entry.type }),
      ),
    )
  }, [pinnedRecordCandidates])
  const invalidatePinnedRecords = async () => {
    await queryClient.invalidateQueries({
      queryKey: ["profile-pinned-records", playerSteamid64],
    })
  }
  const pinRecordMutation = useMutation({
    mutationFn: async ({
      mapId,
      type,
    }: {
      mapId: number
      type: "NUB" | "PRO"
    }) => {
      if (!playerSteamid64) {
        throw new Error("Missing player")
      }
      await pinProfileRecord({
        identifier: playerSteamid64,
        mapId,
        scope,
        type,
      })
    },
    onSuccess: async () => {
      await invalidatePinnedRecords()
      toast.success(t("profile.ban.recordPinned"))
    },
    onError: () => {
      toast.error(t("profile.ban.pinFailed"))
    },
  })
  const unpinRecordMutation = useMutation({
    mutationFn: async ({
      mapId,
      type,
    }: {
      mapId: number
      type: "NUB" | "PRO"
    }) => {
      if (!playerSteamid64) {
        throw new Error("Missing player")
      }
      await unpinProfileRecord({
        identifier: playerSteamid64,
        mapId,
        scope,
        type,
      })
    },
    onSuccess: async () => {
      await invalidatePinnedRecords()
      toast.success(t("profile.ban.recordUnpinned"))
    },
    onError: () => {
      toast.error(t("profile.ban.unpinFailed"))
    },
  })
  const unbanCheckMutation = useMutation({
    mutationFn: async () => {
      if (!playerSteamid64) {
        throw new Error("Missing player")
      }
      return await checkProfileUnbanStatus({
        identifier: playerSteamid64,
      })
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({
        queryKey: ["profile-active-bans", playerSteamid64],
      })

      if (result.remaining_active_ban_count === 0) {
        toast.success(t("profile.ban.statusUpdated"), {
          description:
            result.cleared_ban_count > 0
              ? t("profile.ban.noLongerBanned")
              : result.message,
        })
        return
      }

      toast.info(t("profile.ban.statusChecked"), {
        description:
          result.cleared_ban_count > 0
            ? `${result.message} ${t("profile.ban.activeRemain", {
                count: result.remaining_active_ban_count,
              })}`
            : result.message,
      })
    },
    onError: (error) => {
      toast.error(t("profile.ban.statusCheckFailed"), {
        description: extractErrorMessage(error),
      })
    },
  })
  const syncFriendsMutation = useMutation({
    mutationFn: async () => {
      if (!playerSteamid64) {
        throw new Error("Missing player")
      }
      return await syncProfileFriends({
        identifier: playerSteamid64,
      })
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({
        queryKey: ["profile-friends", canonicalIdentifier],
      })
      if (result.sync.visibility === "public") {
        toast.success(t("profile.friends.synced"))
      }
    },
    onError: async (error) => {
      await queryClient.invalidateQueries({
        queryKey: ["profile-friends", canonicalIdentifier],
      })
      const message = extractErrorMessage(error).replace(
        /^Friends sync is rate limited\.\s*/u,
        "",
      )
      toast.error(t("profile.friends.syncFailed"), {
        description: message,
      })
    },
  })
  const likePlayerMutation = useMutation({
    mutationFn: async () => {
      if (!playerSteamid64) {
        throw new Error("Missing player")
      }
      return await createProfileLike(playerSteamid64)
    },
    onSuccess: (result: ProfileLikeResult) => {
      queryClient.setQueryData(
        ["profile-player-likes", playerSteamid64],
        result,
      )
      if (!result.created) {
        toast.warning(t("profile.likes.alreadyLikedToday"))
      }
    },
    onError: (error) => {
      toast.error(t("profile.likes.likeFailed"), {
        description: extractErrorMessage(error),
      })
    },
  })
  const summary = useMemo(() => {
    const totalPoints = buildProfileTotalPoints({
      nubRecords: nubRecordsQuery.data ?? [],
      proRecords: proRecordsQuery.data ?? [],
    })

    return {
      totalPoints,
      rankLabel: getRatingRankLabel(pointsStandingQuery.data?.rating),
      globalStanding: pointsStandingQuery.data?.rank ?? null,
      regionalStanding: pointsStandingQuery.data?.regionalRank ?? null,
      region: pointsStandingQuery.data?.region ?? null,
      rating: pointsStandingQuery.data?.rating ?? null,
    }
  }, [nubRecordsQuery.data, pointsStandingQuery.data, proRecordsQuery.data])
  const completionTrophies = useMemo(() => {
    return {
      nub: buildProfileTrophyCounts(nubRecordsQuery.data ?? []),
      pro: buildProfileTrophyCounts(proRecordsQuery.data ?? []),
    }
  }, [nubRecordsQuery.data, proRecordsQuery.data])
  const nubRecordDistribution = useMemo(() => {
    return buildProfileRecordDistribution(nubRecordsQuery.data ?? [])
  }, [nubRecordsQuery.data])
  const proRecordDistribution = useMemo(() => {
    return buildProfileRecordDistribution(proRecordsQuery.data ?? [])
  }, [proRecordsQuery.data])

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

  useEffect(() => {
    if (
      activeTab !== "friends" ||
      !isOwnProfile ||
      !playerSteamid64 ||
      friendsQuery.isLoading ||
      friendsQuery.isError ||
      !friendsQuery.data
    ) {
      return
    }
    if (friendsQuery.data.sync.last_attempted_at !== null) {
      return
    }
    if (autoSyncedFriendsRef.current.has(playerSteamid64)) {
      return
    }
    if (syncFriendsMutation.isPending) {
      return
    }

    autoSyncedFriendsRef.current.add(playerSteamid64)
    void syncFriendsMutation.mutateAsync()
  }, [
    activeTab,
    friendsQuery.data,
    friendsQuery.isError,
    friendsQuery.isLoading,
    isOwnProfile,
    playerSteamid64,
    syncFriendsMutation,
  ])

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
  const hasPermanentBan = activeBans.some((ban) => ban.expires_at == null)
  const showBanWarning = activeBanCount > 0
  const showUnbanCheckButton = isOwnProfile && showBanWarning
  const profileTabsTrailingContent =
    activeTab === "records" ? (
      <Label
        htmlFor="profile-records-pro-only"
        className="flex h-9 w-fit items-center justify-start gap-2 rounded-lg border border-border/70 bg-background/80 px-3 text-[11px] font-medium tracking-[0.08em] text-foreground/80 uppercase"
      >
        <Switch
          id="profile-records-pro-only"
          checked={isProOnly}
          onCheckedChange={setIsProOnly}
          className="data-[state=unchecked]:bg-[#f3c40f] data-[state=unchecked]:shadow-[#f3c40f]/35 data-[state=checked]:bg-[#3598db] data-[state=checked]:shadow-[#3598db]/35 dark:data-[state=checked]:bg-[#3598db]"
        />
        <span>{isProOnly ? "PRO" : "NUB"}</span>
      </Label>
    ) : null

  return (
    <div className="space-y-8">
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
          <AlertTitle>{t("profile.ban.warningTitle")}</AlertTitle>
          <AlertDescription
            className={cn(
              "gap-3",
              hasPermanentBan
                ? "text-destructive/90"
                : "text-amber-800 dark:text-amber-200",
            )}
          >
            <div className="grid gap-3">
              {showUnbanCheckButton ? (
                <div className="flex justify-start">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    data-testid="profile-unban-check-button"
                    disabled={unbanCheckMutation.isPending}
                    onClick={() => {
                      if (unbanCheckMutation.isPending) {
                        return
                      }
                      void unbanCheckMutation.mutateAsync()
                    }}
                  >
                    {unbanCheckMutation.isPending
                      ? t("profile.ban.checking")
                      : t("profile.ban.checkUnbanStatus")}
                  </Button>
                </div>
              ) : null}
              {activeBans.map((ban) => (
                <div
                  key={ban.uuid}
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
                      value={ban.created_at}
                      display="absolute"
                      fallback={t("profile.unknownDate")}
                    />
                    <span className="text-muted-foreground">•</span>
                    <span>
                      {ban.expires_at == null
                        ? t("profile.ban.permanent")
                        : t("profile.ban.temporary")}
                    </span>
                  </div>
                  <p className="mt-2 text-sm">
                    {ban.notes?.trim() ? ban.notes : t("profile.ban.noNotes")}
                  </p>
                </div>
              ))}
            </div>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid min-w-0 gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="min-w-0">
          <ProfileSidebar
            identifier={canonicalIdentifier}
            likeMutationPending={likePlayerMutation.isPending}
            onLike={() => {
              if (!isLoggedIn()) {
                void navigate({ to: "/login" })
                return
              }

              likePlayerMutation.mutate()
            }}
            player={player}
            playerLikes={profileLikesQuery.data?.player_likes ?? 0}
            playerLikesError={profileLikesQuery.isError}
            playerLikesLoading={profileLikesQuery.isLoading}
            playtimeError={playerStatsQuery.isError}
            playtimeLoading={playerStatsQuery.isLoading}
            playtimeSeconds={
              playerStatsQuery.data?.playtime?.total_seconds ?? null
            }
            profileViews={profileViewsQuery.data?.profile_views ?? 0}
            profileViewsError={profileViewsQuery.isError}
            profileViewsLoading={profileViewsQuery.isLoading}
            summary={summary}
            summaryLoading={summaryLoading}
          />
        </aside>

        <section className="min-w-0 space-y-6">
          <ProfileCompletionSection
            completion={completion}
            completionLoading={completionLoading}
            completionError={completionError}
            completionTrophies={completionTrophies}
          />

          <ProfileTabs
            activeTab={activeTab}
            identifier={canonicalIdentifier}
            trailingContent={profileTabsTrailingContent}
          />

          {activeTab === "home" ? (
            <>
              <ProfileHomeContent
                activityError={playerStatsQuery.isError}
                activityLoading={playerStatsQuery.isLoading}
                activityStat={playerStatsQuery.data?.daily_activity ?? null}
                canManagePinnedRecords={isOwnProfile}
                nubRecordDistribution={nubRecordDistribution}
                pinnedRecords={pinnedRecords}
                pinnedRecordsError={
                  pinnedRecordsQuery.isError || pinnedRecordRanksQuery.isError
                }
                pinnedRecordsLoading={
                  pinnedRecordsQuery.isLoading ||
                  pinnedRecordRanksQuery.isLoading
                }
                pinnedRecordsMutating={
                  pinRecordMutation.isPending || unpinRecordMutation.isPending
                }
                proRecordDistribution={proRecordDistribution}
                recordDistributionError={
                  nubRecordsQuery.isError || proRecordsQuery.isError
                }
                recordDistributionLoading={
                  nubRecordsQuery.isLoading || proRecordsQuery.isLoading
                }
                onUnpinRecord={(mapId, type) => {
                  unpinRecordMutation.mutate({ mapId, type })
                }}
              />
              <ProfileCommentsTab
                identifier={canonicalIdentifier}
                targetSteamid64={player.steamid64}
              />
            </>
          ) : activeTab === "records" ? (
            <ProfileRecordsTab
              steamid64={player.steamid64}
              isProOnly={isProOnly}
              canManagePinnedRecords={isOwnProfile}
              pinnedRecordKeys={pinnedRecordKeys}
              pinnedRecordsMutating={
                pinRecordMutation.isPending || unpinRecordMutation.isPending
              }
              onPinRecord={(mapId, type) => {
                pinRecordMutation.mutate({ mapId, type })
              }}
              onUnpinRecord={(mapId, type) => {
                unpinRecordMutation.mutate({ mapId, type })
              }}
            />
          ) : activeTab === "unfinished" ? (
            <ProfileUnfinishedTab
              isProOnly={isProOnly}
              maps={mapsQuery.data ?? []}
              mapsLoading={mapsQuery.isLoading}
              mapsError={mapsQuery.isError}
              nubRecords={nubRecordsQuery.data ?? []}
              nubRecordsLoading={nubRecordsQuery.isLoading}
              nubRecordsError={nubRecordsQuery.isError}
              onIsProOnlyChange={setIsProOnly}
              proRecords={proRecordsQuery.data ?? []}
              proRecordsLoading={proRecordsQuery.isLoading}
              proRecordsError={proRecordsQuery.isError}
            />
          ) : activeTab === "friends" ? (
            <ProfileFriendsTab
              friends={friendsQuery.data?.data ?? []}
              friendsCount={friendsQuery.data?.count ?? 0}
              sync={friendsQuery.data?.sync ?? null}
              loading={friendsQuery.isLoading}
              error={friendsQuery.isError}
              actions={
                isOwnProfile ? (
                  <Button
                    type="button"
                    size="sm"
                    data-testid="profile-friends-sync-button"
                    disabled={syncFriendsMutation.isPending}
                    onClick={() => {
                      if (syncFriendsMutation.isPending) {
                        return
                      }
                      void syncFriendsMutation.mutateAsync()
                    }}
                  >
                    {syncFriendsMutation.isPending
                      ? t("profile.friends.syncing")
                      : t("profile.friends.syncButton")}
                  </Button>
                ) : null
              }
            />
          ) : activeTab === "jumpstats" ? (
            <ProfileJumpstatsTab identifier={canonicalIdentifier} />
          ) : (
            <ProfileStatsContent
              error={playerStatsQuery.isError}
              loading={playerStatsQuery.isLoading}
              mostPlayedServer={
                playerStatsQuery.data?.most_played_server ?? null
              }
            />
          )}
        </section>
      </div>
    </div>
  )
}
