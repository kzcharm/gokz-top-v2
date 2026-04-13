import { useQuery } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { useState } from "react"

import { type MapPublic, MapsService } from "@/client"
import { CountryPicker } from "@/components/Common/CountryPicker"
import ErrorComponent from "@/components/Common/ErrorComponent"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { getMapImageUrl } from "@/components/Common/MapDisplay"
import NotFound from "@/components/Common/NotFound"
import { RegionBadge } from "@/components/Common/RegionFlag"
import { getMapPbRecordsQueryOptions } from "@/components/Records/pb-records-utils"
import { TierBadge } from "@/components/Servers/TierBadge"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { getRegionsQueryOptions } from "@/lib/regions"
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

function MapHero({ map, tier }: { map: MapPublic; tier: number | null }) {
  const imageUrl = getMapImageUrl(map.name)
  const authorsList = map.authors ?? []
  const authors =
    authorsList.length > 0 ? authorsList.join(", ") : "Unknown author"

  return (
    <section className="overflow-hidden rounded-[28px] border border-border/70 bg-card shadow-sm">
      <div className="grid gap-6 p-6 sm:p-8 lg:grid-cols-[minmax(280px,0.76fr)_minmax(380px,1.24fr)] lg:items-start">
        <div className="overflow-hidden rounded-2xl border border-border/70 bg-muted">
          <div className="relative aspect-video">
            {imageUrl ? (
              <div
                className="absolute inset-0 bg-cover bg-center"
                style={{ backgroundImage: `url(${imageUrl})` }}
              />
            ) : (
              <div className="absolute inset-0 bg-gradient-to-br from-slate-700 via-slate-800 to-slate-950" />
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/15 to-transparent" />
          </div>
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
                  Open workshop
                </a>
              </Button>
            ) : null}
          </div>

          <dl className="grid gap-4 sm:grid-cols-2">
            <MapMetaItem
              label="Authors"
              value={authors}
              labelClassName="text-muted-foreground"
              valueClassName="text-foreground"
            />
            <MapMetaItem
              label="Workshop ID"
              value={map.workshop_id?.toLocaleString("en-US") ?? "-"}
              labelClassName="text-muted-foreground"
              valueClassName="text-foreground"
            />
            <MapMetaItem
              label="Created"
              value={<FormattedDateTime value={map.created_on} fallback="-" />}
              labelClassName="text-muted-foreground"
              valueClassName="text-foreground"
            />
            <MapMetaItem
              label="Updated"
              value={<FormattedDateTime value={map.updated_on} fallback="-" />}
              labelClassName="text-muted-foreground"
              valueClassName="text-foreground"
            />
          </dl>
        </div>
      </div>
    </section>
  )
}

export function MapDetailPage({ mapName }: { mapName: string }) {
  const { scope } = useScope()
  const [isProOnly, setIsProOnly] = useState(false)
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null)
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState("top")
  const [reviewsPageIndex, setReviewsPageIndex] = useState(0)
  const [reviewsPageSize, setReviewsPageSize] = useState(20)
  const [reviewDialogOpen, setReviewDialogOpen] = useState(false)

  const mapQuery = useQuery({
    queryKey: ["map", mapName],
    queryFn: () => fetchMapByName(mapName),
    retry: false,
  })

  const recordsQuery = useQuery({
    ...getMapPbRecordsQueryOptions({
      mapId: mapQuery.data?.id ?? null,
      scope,
      isProOnly,
      country: selectedCountry,
      region: selectedRegion,
    }),
    enabled: mapQuery.data !== undefined,
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
  return (
    <div className="space-y-6">
      <MapHero map={map} tier={activeTier} />

      <Tabs value={activeTab} onValueChange={setActiveTab} className="gap-4">
        <Card className="gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
          <CardContent className="flex flex-col gap-4 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <TabsList className="w-fit">
                <TabsTrigger value="top">Map Top</TabsTrigger>
                <TabsTrigger value="reviews">Reviews</TabsTrigger>
              </TabsList>

              {activeTab === "top" ? (
                <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-center lg:justify-between">
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <div className="w-full sm:w-[176px]">
                      <CountryPicker
                        value={selectedCountry}
                        onChange={(value) => {
                          setSelectedCountry(value)
                          if (value !== null) {
                            setSelectedRegion(null)
                          }
                        }}
                        placeholder="country"
                        clearLabel="country"
                      />
                    </div>

                    <Select
                      value={selectedRegion ?? "all"}
                      onValueChange={(value) => {
                        const nextRegion = value === "all" ? null : value
                        setSelectedRegion(nextRegion)
                        if (nextRegion !== null) {
                          setSelectedCountry(null)
                        }
                      }}
                    >
                      <SelectTrigger className="w-full sm:w-[144px]">
                        {selectedRegionOption ? (
                          <RegionBadge
                            regionCode={selectedRegionOption.code}
                            regionName={selectedRegionOption.name}
                          />
                        ) : (
                          <span className="text-muted-foreground">region</span>
                        )}
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">region</SelectItem>
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

                  <Label
                    htmlFor="map-records-pro-only"
                    className="flex items-center gap-3 rounded-full border border-border/70 bg-background/70 px-3 py-2"
                  >
                    <Switch
                      id="map-records-pro-only"
                      checked={isProOnly}
                      onCheckedChange={setIsProOnly}
                    />
                    <span>Pro only</span>
                  </Label>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setReviewDialogOpen(true)}
                  data-testid="map-add-review-button"
                >
                  Add Review
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        <TabsContent value="top" className="space-y-6">
          {recordsQuery.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Unable to load map leaderboard</AlertTitle>
              <AlertDescription>
                Reload the page and try again.
              </AlertDescription>
            </Alert>
          ) : null}

          {recordsQuery.isLoading ? (
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
              records={recordsQuery.data ?? []}
              emptyMessage={
                isProOnly
                  ? "No stage 0 pro records found for this map in the selected scope."
                  : "No stage 0 records found for this map in the selected scope."
              }
            />
          )}
        </TabsContent>

        <TabsContent value="reviews" className="space-y-6">
          {reviewsQuery.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Unable to load map reviews</AlertTitle>
              <AlertDescription>
                Reload the page and try again.
              </AlertDescription>
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
