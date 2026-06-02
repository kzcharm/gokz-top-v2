import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Calculator, Copy, LocateFixed, Users } from "lucide-react"
import type { ReactNode } from "react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { FaSteam } from "react-icons/fa"
import { toast } from "sonner"

import {
  type MapPublic,
  MapsService,
  type RecordPublic,
  RecordsService,
} from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import {
  useAdminMode,
  useAdminModeSurface,
} from "@/components/admin-mode-provider"
import { CountryPicker } from "@/components/Common/CountryPicker"
import ErrorComponent from "@/components/Common/ErrorComponent"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { getMapImageUrls } from "@/components/Common/MapDisplay"
import NotFound from "@/components/Common/NotFound"
import { RegionBadge } from "@/components/Common/RegionFlag"
import { TierBadge } from "@/components/Servers/TierBadge"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth from "@/hooks/useAuth"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import useCustomToast from "@/hooks/useCustomToast"
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"
import { formatNumber, getLocale } from "@/i18n/locale"
import { getRegionsQueryOptions } from "@/lib/regions"
import { canModerateBansAndRecords } from "@/lib/user-roles"
import { cn } from "@/lib/utils"
import {
  DeleteCourseRecordsButton,
  useRecordAdminActions,
} from "../Records/admin-actions"
import { MapReviewDialog } from "../Reviews/MapReviewDialog"
import { MapReviewsTable } from "./MapReviewsTable"
import { MapStatsSection } from "./MapStatsSection"
import { MapTopTable } from "./MapTopTable"
import { fetchMapByName } from "./map-utils"

function MapDetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-[220px] rounded-[28px]" />
      <Skeleton className="h-16 rounded-[28px]" />
      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm">
        <div className="space-y-3 p-6">
          <Skeleton className="h-6 w-64" />
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-12 w-full" />
          ))}
        </div>
      </div>
    </div>
  )
}

function MapMetaItem({
  label,
  value,
  labelClassName,
  valueClassName,
}: {
  label: string
  value: ReactNode
  labelClassName?: string
  valueClassName?: string
}) {
  return (
    <div className="space-y-1">
      <dt
        className={`text-xs font-medium uppercase tracking-[0.16em] ${labelClassName ?? "text-white/70"}`}
      >
        {label}
      </dt>
      <dd className={`text-sm font-medium ${valueClassName ?? "text-white"}`}>
        {value}
      </dd>
    </div>
  )
}

function formatRankShare(
  rank: number | null,
  total: number,
  unavailableLabel: string,
  topLabel: string,
) {
  if (rank === null || rank <= 0 || total <= 0) {
    return `${unavailableLabel} / ${formatNumber(total)}`
  }

  const percentage = new Intl.NumberFormat(getLocale(), {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format((rank / total) * 100)

  return `${formatNumber(rank)} / ${formatNumber(total)} (${topLabel} ${percentage}%)`
}

const MAP_RANK_SUMMARY_UNAVAILABLE_LABEL = "-"
const MAP_TAB_OPTIONS = [
  {
    value: "top",
    to: "/maps/$mapName/maptop",
    labelKey: "maps.tabs.top",
  },
  {
    value: "stats",
    to: "/maps/$mapName/stats",
    labelKey: "maps.tabs.stats",
  },
  {
    value: "reviews",
    to: "/maps/$mapName/reviews",
    labelKey: "maps.tabs.reviews",
  },
] as const

type MapDetailTab = (typeof MAP_TAB_OPTIONS)[number]["value"]

type MapPbLeaderboardResponse = {
  data: RecordPublic[]
  count: number
  unique_nub_finishes: number
  unique_pro_finishes: number
  current_user_rank: number | null
  current_user_steamid64: string | null
}

async function fetchMapPbLeaderboardPage({
  mapId,
  scope,
  isProOnly,
  country,
  region,
  offset,
  limit,
  friendsOnly,
}: {
  mapId: number
  scope: string
  isProOnly: boolean
  country: string | null
  region: string | null
  offset: number
  limit: number
  friendsOnly: boolean
}): Promise<MapPbLeaderboardResponse> {
  const accessToken =
    typeof window === "undefined"
      ? null
      : window.localStorage.getItem("access_token")
  const searchParams = new URLSearchParams({
    scope,
    type: isProOnly ? "PRO" : "NUB",
    stage: "0",
    offset: `${offset}`,
    limit: `${limit}`,
  })

  if (country) {
    searchParams.set("country", country)
  }
  if (region) {
    searchParams.set("region", region)
  }
  if (friendsOnly) {
    searchParams.set("friends_only", "true")
  }

  const response = await fetch(
    `${OpenAPI.BASE}/v1/maps/${mapId}/leaderboard?${searchParams.toString()}`,
    {
      credentials: "include",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    },
  )

  if (!response.ok) {
    throw new Error("Failed to load map leaderboard")
  }

  return (await response.json()) as MapPbLeaderboardResponse
}

function MapHero({
  map,
  tier,
  leaderboardSummary,
}: {
  map: MapPublic
  tier: number | null
  leaderboardSummary?: ReactNode
}) {
  const { t } = useTranslation()
  const authorsList = map.authors ?? []
  const authors =
    authorsList.length > 0 ? authorsList.join(", ") : t("maps.unknownAuthor")
  const [, copyToClipboard] = useCopyToClipboard()
  const workshopId =
    map.workshop_id !== null && map.workshop_id !== undefined
      ? String(map.workshop_id)
      : null
  const imageUrls = getMapImageUrls(map.name, workshopId)
  const imageUrlsKey = imageUrls.join("\n")
  const [imageFallback, setImageFallback] = useState({ key: "", index: 0 })
  const imageUrlIndex =
    imageFallback.key === imageUrlsKey ? imageFallback.index : 0
  const imageUrl = imageUrls[imageUrlIndex] ?? null

  const handleImageError = () => {
    setImageFallback((currentFallback) => {
      const currentIndex =
        currentFallback.key === imageUrlsKey ? currentFallback.index : 0
      return {
        key: imageUrlsKey,
        index:
          currentIndex + 1 < imageUrls.length ? currentIndex + 1 : currentIndex,
      }
    })
  }

  const handleCopyWorkshopId = async () => {
    if (!workshopId) {
      return
    }

    const didCopy = await copyToClipboard(workshopId)

    if (didCopy) {
      toast.success(t("common.copied", { label: t("maps.workshopId") }), {
        description: workshopId,
      })
      return
    }

    toast.error(t("common.copyFailed", { label: t("maps.workshopId") }), {
      description: workshopId,
    })
  }

  return (
    <section className="overflow-hidden rounded-[28px] border border-border/70 bg-card shadow-sm">
      <div className="grid gap-6 p-6 sm:p-8 lg:grid-cols-[minmax(280px,0.76fr)_minmax(380px,1.24fr)] lg:items-start">
        <div className="overflow-hidden rounded-2xl border border-border/70 bg-muted leading-none">
          {imageUrl ? (
            <Dialog>
              <DialogTrigger asChild>
                <button
                  type="button"
                  className="relative block aspect-video h-full w-full cursor-zoom-in overflow-hidden leading-none"
                  aria-label={t("maps.zoomImage", { mapName: map.name })}
                >
                  <img
                    src={imageUrl}
                    alt={t("maps.imageAlt", { mapName: map.name })}
                    className="block h-full w-full scale-[1.002] object-cover transition-transform duration-300 hover:scale-[1.022]"
                    onError={handleImageError}
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/15 to-transparent" />
                </button>
              </DialogTrigger>
              <DialogContent
                className="max-w-[min(96vw,72rem)] border-0 bg-transparent p-0 shadow-none sm:max-w-[min(96vw,72rem)]"
                showCloseButton={false}
              >
                <div className="flex justify-center overflow-hidden rounded-[24px] leading-none">
                  <img
                    src={imageUrl}
                    alt={t("maps.imageAltEnlarged", { mapName: map.name })}
                    className="block max-h-[85vh] max-w-full scale-[1.002] rounded-[24px] object-contain"
                    onError={handleImageError}
                  />
                </div>
              </DialogContent>
            </Dialog>
          ) : (
            <div className="relative aspect-video">
              <div className="absolute inset-0 bg-gradient-to-br from-slate-700 via-slate-800 to-slate-950" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/15 to-transparent" />
            </div>
          )}
        </div>

        <div className="space-y-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-3">
                <TierBadge
                  tier={tier}
                  className="px-3 py-1 text-sm shadow-sm"
                  hideWhenUnknown={false}
                />
                <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                  {map.name}
                </h1>
              </div>
            </div>

            {map.workshop_url ? (
              <Button asChild variant="outline" className="rounded-full">
                <a href={map.workshop_url} target="_blank" rel="noreferrer">
                  <FaSteam className="h-4 w-4" aria-hidden="true" />
                  {t("maps.openWorkshop")}
                </a>
              </Button>
            ) : null}
          </div>

          <dl className="grid gap-4 sm:grid-cols-2">
            <MapMetaItem
              label={t("maps.authors")}
              value={authors}
              labelClassName="text-muted-foreground"
              valueClassName="text-foreground"
            />
            <MapMetaItem
              label={t("maps.workshopId")}
              value={
                workshopId ? (
                  <button
                    type="button"
                    className="inline-flex min-h-7 items-center gap-2 rounded-md px-0.5 text-left font-medium text-foreground underline-offset-4 transition-colors hover:text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    title={t("common.copy")}
                    aria-label={`${t("common.copy")} ${t("maps.workshopId")}`}
                    onClick={() => {
                      void handleCopyWorkshopId()
                    }}
                  >
                    <span>{workshopId}</span>
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                ) : (
                  "-"
                )
              }
              labelClassName="text-muted-foreground"
              valueClassName="text-foreground"
            />
            <MapMetaItem
              label={t("maps.created")}
              value={<FormattedDateTime value={map.created_on} fallback="-" />}
              labelClassName="text-muted-foreground"
              valueClassName="text-foreground"
            />
            <MapMetaItem
              label={t("maps.updated")}
              value={<FormattedDateTime value={map.updated_on} fallback="-" />}
              labelClassName="text-muted-foreground"
              valueClassName="text-foreground"
            />
          </dl>

          {leaderboardSummary ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {leaderboardSummary}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  )
}

export function MapDetailPage({
  mapName,
  activeTab,
}: {
  mapName: string
  activeTab: MapDetailTab
}) {
  const { t } = useTranslation()
  const { scope } = useScope()
  const { user: currentUser } = useAuth()
  const { enabled: adminModeEnabled } = useAdminMode()
  const canUseRecordAdminActions = canModerateBansAndRecords(currentUser)
  useAdminModeSurface(canUseRecordAdminActions && activeTab === "top")
  const { bulkDeleteMutation } = useRecordAdminActions()
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [isProOnly, setIsProOnly] = useState(false)
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null)
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [isFriendsOnly, setIsFriendsOnly] = useState(false)
  const [topPageIndex, setTopPageIndex] = useState(0)
  const [topPageSize, setTopPageSize] = usePersistedPageSize({
    storageKey: "gokz-page-size-map-top",
  })
  const [reviewsPageIndex, setReviewsPageIndex] = useState(0)
  const [reviewsPageSize, setReviewsPageSize] = usePersistedPageSize({
    storageKey: "gokz-page-size-map-reviews",
  })
  const [reviewDialogOpen, setReviewDialogOpen] = useState(false)
  const [pendingSpotlightSteamid64, setPendingSpotlightSteamid64] = useState<
    string | null
  >(null)
  const spotlightTimeoutRef = useRef<number | null>(null)
  const spotlightStartTimeoutRef = useRef<number | null>(null)

  const mapQuery = useQuery({
    queryKey: ["map", mapName],
    queryFn: () => fetchMapByName(mapName),
    retry: false,
  })

  const leaderboardQuery = useQuery({
    queryKey: [
      "map",
      "leaderboard",
      mapQuery.data?.id ?? null,
      scope,
      isProOnly,
      selectedCountry,
      selectedRegion,
      isFriendsOnly,
      topPageIndex,
      topPageSize,
    ],
    queryFn: () =>
      fetchMapPbLeaderboardPage({
        mapId: mapQuery.data!.id,
        scope,
        isProOnly,
        country: selectedCountry,
        region: selectedRegion,
        offset: topPageIndex * topPageSize,
        limit: topPageSize,
        friendsOnly: isFriendsOnly,
      }),
    enabled: mapQuery.data !== undefined,
    staleTime: 30_000,
    retry: false,
  })
  const wrQuery = useQuery({
    queryKey: ["map", "wrs", mapQuery.data?.id ?? null, scope, isProOnly],
    queryFn: () =>
      MapsService.readMapWrs({
        mapId: mapQuery.data!.id,
        scope,
        type: isProOnly ? "PRO" : "NUB",
      }),
    enabled: mapQuery.data !== undefined,
    staleTime: 30_000,
    retry: false,
  })
  const oppositeLeaderboardQuery = useQuery({
    queryKey: [
      "map",
      "leaderboard",
      "opposite",
      mapQuery.data?.id ?? null,
      scope,
      isProOnly,
      selectedCountry,
      selectedRegion,
      isFriendsOnly,
      leaderboardQuery.data?.current_user_steamid64 ?? null,
    ],
    queryFn: () =>
      fetchMapPbLeaderboardPage({
        mapId: mapQuery.data!.id,
        scope,
        isProOnly: !isProOnly,
        country: selectedCountry,
        region: selectedRegion,
        offset: 0,
        limit: 1,
        friendsOnly: isFriendsOnly,
      }),
    enabled:
      mapQuery.data !== undefined &&
      leaderboardQuery.data?.current_user_steamid64 !== null,
    staleTime: 30_000,
    retry: false,
  })
  const regionsQuery = useQuery(getRegionsQueryOptions())
  const reviewsQuery = useQuery({
    queryKey: [
      "map",
      "reviews",
      mapQuery.data?.id ?? null,
      reviewsPageIndex,
      reviewsPageSize,
    ],
    queryFn: () =>
      MapsService.readMapReviews({
        mapId: mapQuery.data?.id,
        withCommentsOnly: true,
        offset: reviewsPageIndex * reviewsPageSize,
        limit: reviewsPageSize,
      }),
    enabled: mapQuery.data !== undefined,
    staleTime: 30_000,
  })
  const rebuildPbPointsBucketMutation = useMutation({
    mutationFn: async () => {
      const [nubResponse, proResponse] = await Promise.all([
        RecordsService.rebuildPbPointsBucket({
          mapId: mapQuery.data!.id,
          stage: 0,
          scope,
          type: "NUB",
        }),
        RecordsService.rebuildPbPointsBucket({
          mapId: mapQuery.data!.id,
          stage: 0,
          scope,
          type: "PRO",
        }),
      ])

      return {
        nubUpdatedCount: nubResponse.updated_count,
        proUpdatedCount: proResponse.updated_count,
        updatedCount: nubResponse.updated_count + proResponse.updated_count,
      }
    },
    onSuccess: async (response) => {
      showSuccessToast(
        response.updatedCount === 1
          ? "Recomputed PB points for 1 row across NUB and PRO."
          : `Recomputed PB points for ${response.updatedCount} rows across NUB and PRO.`,
      )
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["map", "leaderboard"] }),
        queryClient.invalidateQueries({ queryKey: ["map", "wrs"] }),
        queryClient.invalidateQueries({ queryKey: ["map", "stats"] }),
      ])
    },
    onError: (error) => {
      showErrorToast(
        error instanceof Error
          ? error.message
          : "Failed to recompute PB points.",
      )
    },
  })
  const statsQuery = useQuery({
    queryKey: ["map", "stats", mapQuery.data?.id ?? null, scope],
    queryFn: () =>
      MapsService.readMapStats({
        mapId: mapQuery.data!.id,
        scope,
      }),
    enabled: mapQuery.data !== undefined,
    staleTime: 30_000,
    retry: false,
  })
  const statsPlayerRecordsQuery = useQuery({
    queryKey: [
      "map",
      "stats",
      "player-records",
      mapQuery.data?.id ?? null,
      scope,
      currentUser?.steamid64 ?? null,
    ],
    queryFn: async () => {
      const viewerSteamid64 = currentUser?.steamid64
      const [nubRecords, proRecords] = await Promise.all([
        RecordsService.readPbRecords({
          mapId: mapQuery.data!.id,
          scope,
          type: "NUB",
          stage: 0,
          identifier: viewerSteamid64!,
          limit: 1,
        }),
        RecordsService.readPbRecords({
          mapId: mapQuery.data!.id,
          scope,
          type: "PRO",
          stage: 0,
          identifier: viewerSteamid64!,
          limit: 1,
        }),
      ])

      return {
        nubTime: nubRecords[0]?.time ?? null,
        proTime: proRecords[0]?.time ?? null,
      }
    },
    enabled:
      mapQuery.data !== undefined && currentUser?.steamid64 !== undefined,
    staleTime: 30_000,
    retry: false,
  })

  useEffect(() => {
    setTopPageIndex(0)
  }, [])

  useEffect(() => {
    return () => {
      if (spotlightStartTimeoutRef.current !== null) {
        window.clearTimeout(spotlightStartTimeoutRef.current)
      }
      if (spotlightTimeoutRef.current !== null) {
        window.clearTimeout(spotlightTimeoutRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (!pendingSpotlightSteamid64) {
      return
    }

    const row = document.querySelector<HTMLTableRowElement>(
      `[data-player-steamid64="${pendingSpotlightSteamid64}"]`,
    )
    if (!row) {
      return
    }

    row.scrollIntoView({
      behavior: "smooth",
      block: "center",
      inline: "nearest",
    })

    if (spotlightStartTimeoutRef.current !== null) {
      window.clearTimeout(spotlightStartTimeoutRef.current)
    }
    if (spotlightTimeoutRef.current !== null) {
      window.clearTimeout(spotlightTimeoutRef.current)
    }

    spotlightStartTimeoutRef.current = window.setTimeout(() => {
      row.classList.remove("leaderboard-self-spotlight")
      void row.getBoundingClientRect()
      row.classList.add("leaderboard-self-spotlight")

      spotlightTimeoutRef.current = window.setTimeout(() => {
        row.classList.remove("leaderboard-self-spotlight")
        spotlightTimeoutRef.current = null
      }, 1800)

      spotlightStartTimeoutRef.current = null
    }, 350)

    setPendingSpotlightSteamid64(null)
  }, [pendingSpotlightSteamid64])

  if (mapQuery.isLoading) {
    return <MapDetailSkeleton />
  }

  if (mapQuery.isError) {
    const status =
      (mapQuery.error as { status?: number } | undefined)?.status ?? null
    if (status === 404) {
      return <NotFound />
    }

    return <ErrorComponent />
  }

  if (!mapQuery.data) {
    return <NotFound />
  }

  const map = mapQuery.data
  const activeTier = map.tiers[scope] ?? 0
  const selectedRegionOption =
    regionsQuery.data?.find((region) => region.code === selectedRegion) ?? null
  const authenticatedUserSteamid64 = currentUser?.steamid64 ?? null
  const canAdministerRecords = adminModeEnabled && canUseRecordAdminActions
  const currentUserSteamid64 =
    leaderboardQuery.data?.current_user_steamid64 ?? null
  const nubRank =
    isProOnly === false
      ? (leaderboardQuery.data?.current_user_rank ?? null)
      : (oppositeLeaderboardQuery.data?.current_user_rank ?? null)
  const proRank =
    isProOnly === true
      ? (leaderboardQuery.data?.current_user_rank ?? null)
      : (oppositeLeaderboardQuery.data?.current_user_rank ?? null)

  const handleFindMe = () => {
    if (!currentUser?.steamid64) {
      toast.warning(t("leaderboards.players.findMe.loginRequiredTitle"), {
        description: t("leaderboards.players.findMe.loginRequiredDescription"),
      })
      return
    }

    const viewerSteamid64 =
      leaderboardQuery.data?.current_user_steamid64 ?? null
    if (!viewerSteamid64) {
      return
    }

    const rank = leaderboardQuery.data?.current_user_rank ?? null
    if (!rank) {
      toast.error(t("maps.findMeNotRankedTitle"), {
        description: t("maps.findMeNotRankedDescription"),
      })
      return
    }

    setPendingSpotlightSteamid64(viewerSteamid64)
    setTopPageIndex(Math.floor((rank - 1) / topPageSize))
  }

  const renderAdminActions = (record: RecordPublic) => (
    <DeleteCourseRecordsButton
      bulkDeleteMutation={bulkDeleteMutation}
      record={record}
    />
  )

  return (
    <div className="space-y-6">
      <MapHero
        map={map}
        tier={activeTier}
        leaderboardSummary={
          !leaderboardQuery.isError ? (
            <>
              <div className="space-y-1">
                <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                  NUB
                </div>
                <div className="text-sm font-semibold text-foreground">
                  {formatRankShare(
                    currentUserSteamid64 ? nubRank : null,
                    leaderboardQuery.data?.unique_nub_finishes ?? 0,
                    MAP_RANK_SUMMARY_UNAVAILABLE_LABEL,
                    t("maps.topPercentPrefix"),
                  )}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                  PRO
                </div>
                <div className="text-sm font-semibold text-foreground">
                  {formatRankShare(
                    currentUserSteamid64 ? proRank : null,
                    leaderboardQuery.data?.unique_pro_finishes ?? 0,
                    MAP_RANK_SUMMARY_UNAVAILABLE_LABEL,
                    t("maps.topPercentPrefix"),
                  )}
                </div>
              </div>
            </>
          ) : null
        }
      />

      <Tabs value={activeTab} className="gap-4">
        <Card className="gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
          <CardContent className="flex flex-col gap-4 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <TabsList className="w-fit">
                {MAP_TAB_OPTIONS.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value} asChild>
                    <Link to={tab.to} params={{ mapName }}>
                      {t(tab.labelKey)}
                    </Link>
                  </TabsTrigger>
                ))}
              </TabsList>

              {activeTab === "top" ? (
                <div className="flex flex-col gap-3 lg:flex-1 lg:flex-row lg:items-center lg:justify-end">
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <div className="w-full sm:w-[176px]">
                      <CountryPicker
                        value={selectedCountry}
                        disabled={isFriendsOnly}
                        onChange={(value) => {
                          setSelectedCountry(value)
                          if (value !== null) {
                            setSelectedRegion(null)
                          }
                          setPendingSpotlightSteamid64(null)
                        }}
                        placeholder={t("maps.filters.country")}
                        clearLabel={t("maps.filters.country")}
                      />
                    </div>

                    <Select
                      disabled={isFriendsOnly}
                      value={selectedRegion ?? "all"}
                      onValueChange={(value) => {
                        const nextRegion = value === "all" ? null : value
                        setSelectedRegion(nextRegion)
                        if (nextRegion !== null) {
                          setSelectedCountry(null)
                        }
                        setPendingSpotlightSteamid64(null)
                      }}
                    >
                      <SelectTrigger className="w-full sm:w-[144px]">
                        {selectedRegionOption ? (
                          <RegionBadge
                            regionCode={selectedRegionOption.code}
                            regionName={selectedRegionOption.name}
                          />
                        ) : (
                          <span className="text-muted-foreground">
                            {t("maps.filters.region")}
                          </span>
                        )}
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">
                          {t("maps.filters.region")}
                        </SelectItem>
                        {(regionsQuery.data ?? []).map((region) => (
                          <SelectItem key={region.code} value={region.code}>
                            <RegionBadge
                              regionCode={region.code}
                              regionName={region.name}
                            />
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    {canAdministerRecords ? (
                      <LoadingButton
                        type="button"
                        variant="outline"
                        loading={rebuildPbPointsBucketMutation.isPending}
                        disabled={mapQuery.data === undefined}
                        onClick={() => rebuildPbPointsBucketMutation.mutate()}
                      >
                        <Calculator />
                        Recompute PB Points
                      </LoadingButton>
                    ) : null}
                    <Button
                      type="button"
                      variant="outline"
                      aria-pressed={isFriendsOnly}
                      className={cn(
                        "border-border/70 bg-background/80",
                        isFriendsOnly &&
                          "border-amber-500/50 bg-amber-500/12 text-amber-950 hover:bg-amber-500/18 dark:text-amber-100",
                      )}
                      onClick={() => {
                        if (!currentUser?.steamid64) {
                          toast.warning(
                            t(
                              "leaderboards.players.friends.loginRequiredTitle",
                            ),
                            {
                              description: t(
                                "leaderboards.players.friends.loginRequiredDescription",
                              ),
                            },
                          )
                          return
                        }

                        const nextValue = !isFriendsOnly
                        setIsFriendsOnly(nextValue)
                        if (nextValue) {
                          setSelectedCountry(null)
                          setSelectedRegion(null)
                        }
                        setPendingSpotlightSteamid64(null)
                        setTopPageIndex(0)
                      }}
                    >
                      <Users />
                      {t("leaderboards.players.friends.label")}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleFindMe}
                      disabled={leaderboardQuery.isLoading}
                    >
                      <LocateFixed />
                      {t("maps.findMe")}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      aria-pressed={isProOnly}
                      className={cn(
                        "border-border/70 bg-background/80",
                        isProOnly
                          ? "border-[#3598db] bg-[#3598db] text-white hover:bg-[#2c84bf] hover:text-white dark:border-[#3598db] dark:bg-[#3598db] dark:text-white"
                          : "border-[#f3c40f] bg-[#f3c40f] text-white hover:bg-[#d8ad0d] hover:text-white dark:border-[#f3c40f] dark:bg-[#f3c40f] dark:text-white",
                      )}
                      onClick={() => {
                        setIsProOnly((currentValue) => !currentValue)
                        setPendingSpotlightSteamid64(null)
                      }}
                    >
                      {isProOnly ? "PRO" : "NUB"}
                    </Button>
                  </div>
                </div>
              ) : activeTab === "reviews" ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setReviewDialogOpen(true)}
                  data-testid="map-add-review-button"
                >
                  {t("maps.addReview")}
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <TabsContent value="top" className="space-y-6">
          {leaderboardQuery.isError ? (
            <Alert variant="destructive">
              <AlertTitle>{t("errors.mapLeaderboardFailed")}</AlertTitle>
              <AlertDescription>{t("common.refresh")}</AlertDescription>
            </Alert>
          ) : null}

          {leaderboardQuery.isLoading ? (
            <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm">
              <div className="space-y-3 p-6">
                <Skeleton className="h-6 w-72" />
                {Array.from({ length: 6 }, (_, index) => (
                  <Skeleton key={index} className="h-12 w-full" />
                ))}
              </div>
            </div>
          ) : (
            <MapTopTable
              records={leaderboardQuery.data?.data ?? []}
              wrTime={wrQuery.data?.[0]?.time ?? null}
              emptyMessage={
                isProOnly ? t("maps.emptyTopPro") : t("maps.emptyTop")
              }
              isLoading={leaderboardQuery.isLoading}
              pageIndex={topPageIndex}
              pageSize={topPageSize}
              totalCount={leaderboardQuery.data?.count ?? 0}
              onPageChange={setTopPageIndex}
              onPageSizeChange={setTopPageSize}
              currentUserSteamid64={authenticatedUserSteamid64}
              renderAdminActions={
                canAdministerRecords ? renderAdminActions : undefined
              }
            />
          )}
        </TabsContent>

        <TabsContent value="stats" className="space-y-6">
          {statsQuery.isError ? (
            <Alert variant="destructive">
              <AlertTitle>{t("maps.stats.loadFailedTitle")}</AlertTitle>
              <AlertDescription>
                {t("maps.stats.loadFailedBody")}
              </AlertDescription>
            </Alert>
          ) : null}

          {statsQuery.isLoading ? (
            <div className="grid gap-6 xl:grid-cols-2">
              {Array.from({ length: 2 }, (_, index) => (
                <Card
                  key={index}
                  className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0"
                >
                  <CardContent className="space-y-5 p-6">
                    <div className="space-y-2">
                      <Skeleton className="h-4 w-44" />
                      <Skeleton className="h-4 w-40" />
                      <Skeleton className="h-4 w-28" />
                    </div>
                    <Skeleton className="h-72 w-full rounded-[18px]" />
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : statsQuery.data ? (
            <MapStatsSection
              stats={statsQuery.data}
              nubPlayerRecordTime={
                statsPlayerRecordsQuery.data?.nubTime ?? null
              }
              proPlayerRecordTime={
                statsPlayerRecordsQuery.data?.proTime ?? null
              }
              showPlayerMarker={authenticatedUserSteamid64 !== null}
            />
          ) : null}
        </TabsContent>

        <TabsContent value="reviews" className="space-y-6">
          {reviewsQuery.isError ? (
            <Alert variant="destructive">
              <AlertTitle>{t("errors.mapReviewsFailed")}</AlertTitle>
              <AlertDescription>{t("common.refresh")}</AlertDescription>
            </Alert>
          ) : null}

          <MapReviewsTable
            mapId={map.id}
            reviews={reviewsQuery.data?.data ?? []}
            totalCount={reviewsQuery.data?.count ?? 0}
            isLoading={reviewsQuery.isLoading}
            pageIndex={reviewsPageIndex}
            pageSize={reviewsPageSize}
            onPageChange={setReviewsPageIndex}
            onPageSizeChange={(nextPageSize) => {
              setReviewsPageIndex(0)
              setReviewsPageSize(nextPageSize)
            }}
          />
        </TabsContent>
      </Tabs>

      <MapReviewDialog
        open={reviewDialogOpen}
        onOpenChange={setReviewDialogOpen}
        mapId={map.id}
        mapName={map.name}
      />
    </div>
  )
}
