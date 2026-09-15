import {
  type InfiniteData,
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { X } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  ApiError,
  type MapPublic,
  MapsService,
  OpenAPI,
  type RecentWrPublic,
  type RecentWrsPublic,
  RecordsService,
  type RecordType,
} from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapNameContextMenu } from "@/components/Common/MapDisplay"
import {
  getPlayerDisplayName,
  PlayerDisplay,
} from "@/components/Common/PlayerDisplay"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { formatRecordTime } from "@/components/Records/utils"
import { TierBadge } from "@/components/Servers/TierBadge"
import { type AppScope, useScope } from "@/components/scope-provider"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { useMapImageUrls } from "@/hooks/useMapImageUrls"
import { cn } from "@/lib/utils"

const RECENT_WRS_BATCH_SIZE = 20
const RECENT_WRS_MAX_CARDS = 100

function buildRecentWrsWebSocketUrl({
  limit,
  mapId,
  scope,
  tier,
  type,
}: {
  limit: number
  mapId: number | null
  scope: AppScope
  tier: number | null
  type: RecordType
}) {
  const configuredBase = OpenAPI.BASE || window.location.origin
  const baseUrl = new URL(configuredBase, window.location.origin)
  const protocol = baseUrl.protocol === "https:" ? "wss:" : "ws:"
  const normalizedPath =
    baseUrl.pathname === "/" ? "" : baseUrl.pathname.replace(/\/$/, "")
  const params = new URLSearchParams({ limit: String(limit), scope })
  if (mapId !== null) params.set("map_id", String(mapId))
  if (tier !== null) params.set("tier", String(tier))
  params.set("type", type)
  return `${protocol}//${baseUrl.host}${normalizedPath}/v1/ws/records/wrs/recent?${params}`
}

function RecentWrCard({
  item,
  highlighted,
  selectedType,
}: {
  item: RecentWrPublic
  highlighted: boolean
  selectedType: RecordType
}) {
  const { t } = useTranslation()
  const { record, achievements } = item
  const playerName = getPlayerDisplayName(record.player)
  const imageUrls = useMapImageUrls(record.map.name)
  const hasNubAchievement = achievements.some(
    (achievement) => achievement.type === "NUB",
  )
  const hasProAchievement = achievements.some(
    (achievement) => achievement.type === "PRO",
  )
  const selectedAchievement =
    achievements.find((achievement) => achievement.type === selectedType) ??
    achievements[0]
  const wrTypeLabel =
    hasNubAchievement && hasProAchievement
      ? "NUB / PRO WR"
      : hasProAchievement
        ? "PRO WR"
        : "NUB WR"

  return (
    <Card
      data-testid={`recent-wr-card-${record.uuid}`}
      className={cn(
        "group gap-0 overflow-hidden rounded-2xl border-border/70 py-0 transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-md motion-reduce:transform-none motion-reduce:transition-none",
        highlighted &&
          "animate-in border-primary/55 bg-primary/[0.035] fade-in slide-in-from-top-2 duration-500 motion-reduce:animate-none",
      )}
    >
      <div
        data-testid="recent-wr-map-preview"
        className="relative aspect-video shrink-0 overflow-hidden bg-muted"
      >
        <Link
          to="/maps/$mapName/maptop"
          params={{ mapName: record.map.name }}
          aria-label={`Open ${record.map.name}`}
          className="block h-full w-full rounded-t-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
        >
          {imageUrls.length > 0 ? (
            <div
              className="absolute inset-0 bg-cover bg-center transition-transform duration-300 group-hover:scale-105 motion-reduce:transition-none"
              style={{
                backgroundImage: imageUrls
                  .map((url) => `url("${url.replace(/"/g, "%22")}")`)
                  .join(", "),
              }}
            />
          ) : null}
          <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-black/35 to-black/85" />
        </Link>

        <div className="absolute top-2 right-16 left-2 z-10 min-w-0">
          <MapNameContextMenu mapName={record.map.name} mapId={record.map.id}>
            {(handlers) => (
              <Link
                to="/maps/$mapName/maptop"
                params={{ mapName: record.map.name }}
                className="inline-block max-w-full truncate rounded-md bg-black/45 px-2 py-1 text-sm font-semibold whitespace-nowrap text-white"
                title={record.map.name}
                onClick={(event) => event.stopPropagation()}
                onContextMenu={handlers.onContextMenu}
                onKeyDown={handlers.onKeyDown}
              >
                {record.map.name}
              </Link>
            )}
          </MapNameContextMenu>
        </div>

        <div className="pointer-events-none absolute top-2 right-2 z-10 shrink-0">
          <TierBadge
            tier={record.map.tier}
            className="bg-black/55 text-white backdrop-blur-sm"
          />
        </div>

        <div className="pointer-events-none absolute top-1/2 right-8 left-8 z-10 flex -translate-y-1/2 flex-col items-center text-center">
          <div
            data-testid="recent-wr-player-name"
            className="mb-0.5 max-w-full truncate text-base font-semibold text-white [text-shadow:_0_1px_3px_rgb(0_0_0_/_0.95)]"
            title={playerName}
          >
            {playerName}
          </div>
          <div
            data-testid="recent-wr-time"
            className="text-2xl font-normal tabular-nums tracking-wide text-white sm:text-3xl"
            style={{
              fontFamily: "Arial, Helvetica, sans-serif",
              textShadow:
                "-1px -1px 0 rgba(0, 0, 0, 0.9), 1px -1px 0 rgba(0, 0, 0, 0.9), -1px 1px 0 rgba(0, 0, 0, 0.9), 1px 1px 0 rgba(0, 0, 0, 0.9), 0 2px 4px rgba(0, 0, 0, 0.8)",
            }}
          >
            {formatRecordTime(record.time)}
          </div>
          {selectedAchievement?.improvement_seconds == null ? (
            <div className="mt-1 font-mono text-xs font-semibold text-emerald-300 [text-shadow:_0_1px_3px_rgb(0_0_0_/_0.9)] sm:text-sm">
              {t("dashboard.wrs.firstWr")}
            </div>
          ) : (
            <div className="mt-1 flex max-w-full items-center justify-center gap-1 font-mono text-xs font-semibold text-emerald-300 [text-shadow:_0_1px_3px_rgb(0_0_0_/_0.9)] sm:text-sm">
              <span className="shrink-0">
                {t("dashboard.wrs.previousPlayerPrefix", {
                  delta: formatRecordTime(
                    selectedAchievement.improvement_seconds,
                  ),
                })}
              </span>
              <span
                data-testid="recent-wr-previous-player"
                className="min-w-0 truncate"
                title={selectedAchievement.previous_player_name ?? undefined}
              >
                {selectedAchievement.previous_player_name ?? "-"}
              </span>
              <span className="shrink-0">
                {t("dashboard.wrs.previousPlayerSuffix")}
              </span>
            </div>
          )}
        </div>

        <div
          data-testid="recent-wr-type"
          className="pointer-events-none absolute bottom-2 left-2 z-10 flex items-center gap-1"
        >
          {hasNubAchievement ? (
            <Badge className="border-transparent bg-[#f2c40f] px-3 py-1 font-semibold text-slate-950">
              {hasProAchievement ? "NUB" : wrTypeLabel}
            </Badge>
          ) : null}
          {hasNubAchievement && hasProAchievement ? (
            <span className="font-semibold text-white"> / </span>
          ) : null}
          {hasProAchievement ? (
            <Badge className="border-transparent bg-[#3598db] px-3 py-1 font-semibold text-white">
              PRO WR
            </Badge>
          ) : null}
        </div>

        <div
          data-testid="recent-wr-created-at"
          className="pointer-events-none absolute right-2 bottom-2 z-10 rounded-md bg-black/55 px-2 py-1 text-right text-xs text-white backdrop-blur-sm"
        >
          <FormattedDateTime
            value={record.created_on}
            display="relative"
            fallback="-"
          />
        </div>
      </div>

      <CardContent className="p-5 sm:p-6">
        <PlayerDisplay
          player={record.player}
          nameMaxLength={28}
          subline={{
            type: "record",
            mode: record.mode.name,
            recordType: selectedType,
            time: record.time,
          }}
        />
      </CardContent>
    </Card>
  )
}

function RecentWrSkeletons({ count = 8 }: { count?: number }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: count }, (_, index) => (
        <Card key={index} className="gap-0 overflow-hidden rounded-2xl py-0">
          <Skeleton className="aspect-video w-full shrink-0 rounded-none" />
          <div className="p-6">
            <Skeleton className="h-9 w-full" />
          </div>
        </Card>
      ))}
    </div>
  )
}

function MapFilter({
  inputValue,
  maps,
  onInputChange,
  onSelect,
  selectedMap,
}: {
  inputValue: string
  maps: MapPublic[]
  onInputChange: (value: string) => void
  onSelect: (map: MapPublic | null) => void
  selectedMap: MapPublic | null
}) {
  const { t } = useTranslation()
  const [focused, setFocused] = useState(false)
  const matches = useMemo(() => {
    const query = inputValue.trim().toLocaleLowerCase()
    if (!query || selectedMap) return []
    return maps
      .filter((map) => map.name.toLocaleLowerCase().includes(query))
      .slice(0, 8)
  }, [inputValue, maps, selectedMap])

  return (
    <div className="relative w-full sm:w-64">
      <Input
        role="combobox"
        aria-expanded={focused && matches.length > 0}
        aria-controls="recent-wrs-map-options"
        value={selectedMap?.name ?? inputValue}
        onChange={(event) => {
          onSelect(null)
          onInputChange(event.target.value)
        }}
        onFocus={() => setFocused(true)}
        onBlur={() => window.setTimeout(() => setFocused(false), 100)}
        placeholder={t("dashboard.wrs.filters.map")}
        aria-label={t("dashboard.wrs.filters.map")}
        className="pr-9"
      />
      {selectedMap ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="absolute top-0.5 right-0.5 size-8"
          aria-label={t("common.clear")}
          onClick={() => {
            onSelect(null)
            onInputChange("")
          }}
        >
          <X className="size-4" />
        </Button>
      ) : null}
      {focused && inputValue.trim() && !selectedMap ? (
        <div
          id="recent-wrs-map-options"
          role="listbox"
          className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-md border border-border bg-popover p-1 shadow-md"
        >
          {matches.length > 0 ? (
            matches.map((map) => (
              <button
                key={map.id}
                type="button"
                role="option"
                aria-selected={false}
                className="w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent focus:bg-accent focus:outline-none"
                onMouseDown={(event) => {
                  event.preventDefault()
                  onSelect(map)
                  onInputChange(map.name)
                  setFocused(false)
                }}
              >
                {map.name}
              </button>
            ))
          ) : (
            <div className="px-2 py-2 text-sm text-muted-foreground">
              {t("dashboard.wrs.filters.noMaps")}
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}

export function RecentWrsPanel() {
  const { t } = useTranslation()
  const { scope } = useScope()
  const queryClient = useQueryClient()
  const loadMoreRef = useRef<HTMLDivElement>(null)
  const [mapInput, setMapInput] = useState("")
  const [selectedMap, setSelectedMap] = useState<MapPublic | null>(null)
  const [tier, setTier] = useState<TierSelectorValue>("all")
  const [type, setType] = useState<RecordType>("NUB")
  const [highlightedUuid, setHighlightedUuid] = useState<string | null>(null)

  const mapsQuery = useQuery({
    queryKey: ["maps", "picker", "validated"],
    queryFn: () =>
      MapsService.readMaps({ offset: 0, limit: 100000, isValidated: true }),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  })
  const filters = useMemo(
    () => ({
      scope,
      mapId: selectedMap?.id ?? null,
      tier: tier === "all" ? null : Number(tier),
      type,
    }),
    [scope, selectedMap?.id, tier, type],
  )
  const queryKey = ["recent-wrs", filters] as const
  const wrsQuery = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) =>
      RecordsService.readRecentWrs({
        offset: pageParam,
        limit: Math.min(
          RECENT_WRS_BATCH_SIZE,
          RECENT_WRS_MAX_CARDS - pageParam,
        ),
        scope,
        mapId: filters.mapId ?? undefined,
        tier: filters.tier ?? undefined,
        type,
      }),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 503) && failureCount < 1,
    initialPageParam: 0,
    getNextPageParam: (lastPage, _pages, lastPageParam) => {
      const nextOffset = lastPageParam + RECENT_WRS_BATCH_SIZE
      const cappedCount = Math.min(lastPage.count, RECENT_WRS_MAX_CARDS)
      return lastPage.data.length > 0 && nextOffset < cappedCount
        ? nextOffset
        : undefined
    },
  })
  const { fetchNextPage, hasNextPage, isFetchingNextPage } = wrsQuery

  useEffect(() => {
    const target = loadMoreRef.current
    if (!target || !hasNextPage || isFetchingNextPage) {
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          void fetchNextPage()
        }
      },
      { rootMargin: "320px 0px" },
    )

    observer.observe(target)
    return () => observer.disconnect()
  }, [fetchNextPage, hasNextPage, isFetchingNextPage])

  useEffect(() => {
    if (wrsQuery.isError) return
    let websocket: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | null = null
    let closed = false
    let attempt = 0
    let receivedInitialSnapshot = false
    const connect = () => {
      websocket = new WebSocket(
        buildRecentWrsWebSocketUrl({
          ...filters,
          limit: RECENT_WRS_BATCH_SIZE,
        }),
      )
      websocket.onopen = () => {
        attempt = 0
      }
      websocket.onmessage = (message) => {
        try {
          const snapshot = JSON.parse(message.data) as RecentWrsPublic & {
            type: string
          }
          if (snapshot.type !== "recent_wrs.snapshot") return
          const cacheKey = ["recent-wrs", filters] as const
          const firstUuid = snapshot.data[0]?.record.uuid ?? null
          const previous =
            queryClient.getQueryData<InfiniteData<RecentWrsPublic, number>>(
              cacheKey,
            )
          const previousUuid = previous?.pages[0]?.data[0]?.record.uuid ?? null
          const firstPage = {
            data: snapshot.data.slice(0, RECENT_WRS_BATCH_SIZE),
            count: snapshot.count,
          }
          const firstRecordChanged = firstUuid !== previousUuid
          queryClient.setQueryData<InfiniteData<RecentWrsPublic, number>>(
            cacheKey,
            firstRecordChanged || !previous
              ? { pages: [firstPage], pageParams: [0] }
              : {
                  pages: [firstPage, ...previous.pages.slice(1)],
                  pageParams: previous.pageParams,
                },
          )
          if (firstUuid && firstRecordChanged && receivedInitialSnapshot) {
            setHighlightedUuid(firstUuid)
            window.setTimeout(() => setHighlightedUuid(null), 1800)
          }
          receivedInitialSnapshot = true
        } catch {
          websocket?.close()
        }
      }
      websocket.onclose = () => {
        if (closed) return
        attempt += 1
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempt, 15000))
      }
      websocket.onerror = () => websocket?.close()
    }
    connect()
    return () => {
      closed = true
      if (timer) clearTimeout(timer)
      websocket?.close()
    }
  }, [filters, queryClient, wrsQuery.isError])

  const data = useMemo(() => {
    const seen = new Set<string>()
    const items: RecentWrPublic[] = []
    for (const page of wrsQuery.data?.pages ?? []) {
      for (const item of page.data) {
        if (seen.has(item.record.uuid)) continue
        seen.add(item.record.uuid)
        items.push(item)
        if (items.length === RECENT_WRS_MAX_CARDS) return items
      }
    }
    return items
  }, [wrsQuery.data?.pages])
  const isPreparing =
    wrsQuery.error instanceof ApiError && wrsQuery.error.status === 503

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-card/70 p-4 sm:flex-row sm:flex-wrap sm:items-center">
        <MapFilter
          inputValue={mapInput}
          maps={mapsQuery.data ?? []}
          selectedMap={selectedMap}
          onInputChange={setMapInput}
          onSelect={setSelectedMap}
        />
        <TierSelector
          value={tier}
          onValueChange={setTier}
          allLabel={t("dashboard.wrs.filters.tier")}
          ariaLabel={t("dashboard.wrs.filters.tier")}
          showAllLabelInTrigger
          triggerClassName="h-9 w-full min-w-24 border-border/70 bg-background/80 px-3 text-sm sm:w-auto"
        />
        <Button
          type="button"
          variant="outline"
          aria-pressed={type === "PRO"}
          aria-label={t("dashboard.wrs.filters.type")}
          className={cn(
            "w-full border-border/70 bg-background/80 sm:w-auto",
            type === "PRO"
              ? "border-[#3598db] bg-[#3598db] text-white hover:bg-[#2c84bf] hover:text-white dark:border-[#3598db] dark:bg-[#3598db] dark:text-white"
              : "border-[#f3c40f] bg-[#f3c40f] text-white hover:bg-[#d8ad0d] hover:text-white dark:border-[#f3c40f] dark:bg-[#f3c40f] dark:text-white",
          )}
          onClick={() => {
            setType((currentType) => (currentType === "PRO" ? "NUB" : "PRO"))
          }}
        >
          {type}
        </Button>
      </div>

      {isPreparing ? (
        <Alert>
          <AlertDescription>{t("dashboard.wrs.preparing")}</AlertDescription>
        </Alert>
      ) : wrsQuery.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{t("dashboard.wrs.loadFailed")}</AlertDescription>
        </Alert>
      ) : wrsQuery.isLoading ? (
        <RecentWrSkeletons />
      ) : data.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border px-6 py-20 text-center text-muted-foreground">
          {t("dashboard.wrs.noMatches")}
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {data.map((item) => (
              <RecentWrCard
                key={item.record.uuid}
                item={item}
                highlighted={item.record.uuid === highlightedUuid}
                selectedType={type}
              />
            ))}
          </div>
          {hasNextPage ? (
            <div
              ref={loadMoreRef}
              data-testid="recent-wrs-load-more"
              className="min-h-1"
              aria-hidden="true"
            />
          ) : null}
          {isFetchingNextPage ? <RecentWrSkeletons count={4} /> : null}
        </>
      )}
    </div>
  )
}
