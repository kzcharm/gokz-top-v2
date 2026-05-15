import { useQuery } from "@tanstack/react-query"
import { LocateFixed, Users } from "lucide-react"
import type { ReactNode } from "react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { type MapPublic, MapsService, type RecordPublic } from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { CountryPicker } from "@/components/Common/CountryPicker"
import ErrorComponent from "@/components/Common/ErrorComponent"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { getMapImageUrl } from "@/components/Common/MapDisplay"
import NotFound from "@/components/Common/NotFound"
import { RegionBadge } from "@/components/Common/RegionFlag"
import { TierBadge } from "@/components/Servers/TierBadge"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth from "@/hooks/useAuth"
import { formatNumber, getLocale } from "@/i18n/locale"
import { getRegionsQueryOptions } from "@/lib/regions"
import { cn } from "@/lib/utils"
import { MapReviewDialog } from "../Reviews/MapReviewDialog"
import { MapReviewsTable } from "./MapReviewsTable"
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
  const imageUrl = getMapImageUrl(map.name)
  const authorsList = map.authors ?? []
  const authors =
    authorsList.length > 0 ? authorsList.join(", ") : t("maps.unknownAuthor")

  return (
    <section className="overflow-hidden rounded-[28px] border border-border/70 bg-card shadow-sm">
      <div className="grid gap-6 p-6 sm:p-8 lg:grid-cols-[minmax(280px,0.76fr)_minmax(380px,1.24fr)] lg:items-start">
        <div className="overflow-hidden rounded-2xl border border-border/70 bg-muted">
          {imageUrl ? (
            <Dialog>
              <DialogTrigger asChild>
                <button
                  type="button"
                  className="relative aspect-video w-full cursor-zoom-in overflow-hidden"
                  aria-label={t("maps.zoomImage", { mapName: map.name })}
                >
                  <img
                    src={imageUrl}
                    alt={t("maps.imageAlt", { mapName: map.name })}
                    className="h-full w-full object-cover transition-transform duration-300 hover:scale-[1.02]"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/15 to-transparent" />
                </button>
              </DialogTrigger>
              <DialogContent
                className="max-w-[min(96vw,72rem)] border-0 bg-transparent p-0 shadow-none sm:max-w-[min(96vw,72rem)]"
                showCloseButton={false}
              >
                <div className="flex justify-center overflow-hidden rounded-[24px]">
                  <img
                    src={imageUrl}
                    alt={t("maps.imageAltEnlarged", { mapName: map.name })}
                    className="max-h-[85vh] max-w-full rounded-[24px] object-contain"
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
                map.workshop_id !== null && map.workshop_id !== undefined
                  ? formatNumber(map.workshop_id)
                  : "-"
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
            <div className="grid gap-3 sm:grid-cols-2">{leaderboardSummary}</div>
          ) : null}
        </div>
      </div>
    </section>
  )
}

export function MapDetailPage({ mapName }: { mapName: string }) {
  const { t } = useTranslation()
  const { scope } = useScope()
  const { user: currentUser } = useAuth()
  const [isProOnly, setIsProOnly] = useState(false)
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null)
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [isFriendsOnly, setIsFriendsOnly] = useState(false)
  const [activeTab, setActiveTab] = useState("top")
  const [topPageIndex, setTopPageIndex] = useState(0)
  const [topPageSize, setTopPageSize] = useState(20)
  const [reviewsPageIndex, setReviewsPageIndex] = useState(0)
  const [reviewsPageSize, setReviewsPageSize] = useState(20)
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

  useEffect(() => {
    setTopPageIndex(0)
  }, [
    mapQuery.data?.id,
    scope,
    isProOnly,
    selectedCountry,
    selectedRegion,
    isFriendsOnly,
  ])

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
  }, [leaderboardQuery.data?.data, pendingSpotlightSteamid64])

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
  const activeTier = map.tiers[scope]
  const selectedRegionOption =
    regionsQuery.data?.find((region) => region.code === selectedRegion) ?? null
  const currentUserSteamid64 =
    leaderboardQuery.data?.current_user_steamid64 ?? null
  const nubRank =
    isProOnly === false
      ? leaderboardQuery.data?.current_user_rank ?? null
      : oppositeLeaderboardQuery.data?.current_user_rank ?? null
  const proRank =
    isProOnly === true
      ? leaderboardQuery.data?.current_user_rank ?? null
      : oppositeLeaderboardQuery.data?.current_user_rank ?? null

  const handleFindMe = () => {
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
                    t("common.notAvailable"),
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
                    t("common.notAvailable"),
                    t("maps.topPercentPrefix"),
                  )}
                </div>
              </div>
            </>
          ) : null
        }
      />

      <Tabs value={activeTab} onValueChange={setActiveTab} className="gap-4">
        <Card className="gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
          <CardContent className="flex flex-col gap-4 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <TabsList className="w-fit">
                <TabsTrigger value="top">{t("maps.tabs.top")}</TabsTrigger>
                <TabsTrigger value="reviews">
                  {t("maps.tabs.reviews")}
                </TabsTrigger>
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
                            t("leaderboards.players.friends.loginRequiredTitle"),
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
                    {currentUserSteamid64 ? (
                      <Button
                        type="button"
                        variant="outline"
                        onClick={handleFindMe}
                        disabled={leaderboardQuery.isLoading}
                      >
                        <LocateFixed />
                        {t("maps.findMe")}
                      </Button>
                    ) : null}
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
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setReviewDialogOpen(true)}
                  data-testid="map-add-review-button"
                >
                  {t("maps.addReview")}
                </Button>
              )}
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
              emptyMessage={
                isProOnly ? t("maps.emptyTopPro") : t("maps.emptyTop")
              }
              isLoading={leaderboardQuery.isLoading}
              pageIndex={topPageIndex}
              pageSize={topPageSize}
              totalCount={leaderboardQuery.data?.count ?? 0}
              onPageChange={setTopPageIndex}
              onPageSizeChange={setTopPageSize}
              currentUserSteamid64={
                leaderboardQuery.data?.current_user_steamid64 ?? null
              }
            />
          )}
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
