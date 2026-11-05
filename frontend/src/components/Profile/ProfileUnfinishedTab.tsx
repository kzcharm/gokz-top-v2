import { useQuery } from "@tanstack/react-query"
import { ArrowDown, ArrowUp } from "lucide-react"
import {
  memo,
  type ReactNode,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { useTranslation } from "react-i18next"
import {
  LeaderboardsService,
  type MapPublic,
  type RecordPublic,
} from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { RecordTypeTabs } from "@/components/Common/RecordTypeTabs"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { useGlobalPreferences } from "@/components/global-preferences-provider"
import { ReviewSummaryRow } from "@/components/Maps/MapOverviewSections"
import { formatRecordTime } from "@/components/Records/utils"
import { TierBadge } from "@/components/Servers/TierBadge"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useHiddenMaps } from "@/hooks/useHiddenMaps"
import { formatNumber } from "@/i18n/locale"

import {
  type ProfileUnfinishedRow as BaseUnfinishedRow,
  buildProfileUnfinishedRows,
  getProfileMapWrsQueryOptions,
} from "./profile-utils"

const PROFILE_UNFINISHED_PAGE_SIZE = 100

type ProfileUnfinishedRow = BaseUnfinishedRow & {
  nubFinishers: number | null
  proFinishers: number | null
  createdAt: number | null
  firstMedian: number | null
  medianPbTime: number | null
  overallRating: number | null
  reviewsCount: number
}

type ProfileUnfinishedType = "NUB" | "PRO"
type ProfileUnfinishedSortColumn =
  | "map"
  | "tier"
  | "wrTime"
  | "nubFinishers"
  | "proFinishers"
  | "createdAt"
  | "firstMedian"
  | "medianPbTime"
  | "overallRating"
type ProfileUnfinishedSortDirection = "asc" | "desc"

type ProfileUnfinishedSortState = {
  column: ProfileUnfinishedSortColumn
  direction: ProfileUnfinishedSortDirection
}

// Keep the view during navigation; a full page reload starts a fresh view.
let unfinishedView:
  | {
      mapSearch: string
      selectedTier: TierSelectorValue
      nubSort: ProfileUnfinishedSortState
      proSort: ProfileUnfinishedSortState
      isProOnly: boolean
    }
  | undefined

function compareText(left: string, right: string) {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  })
}

function sortProfileUnfinishedRows(
  rows: ProfileUnfinishedRow[],
  sort: ProfileUnfinishedSortState,
) {
  return [...rows].sort((left, right) => {
    let comparison = 0

    switch (sort.column) {
      case "map":
        comparison = compareText(left.mapName, right.mapName)
        break
      case "tier":
        comparison = left.tier - right.tier
        break
      default: {
        const leftValue = left[sort.column]
        const rightValue = right[sort.column]
        if (leftValue === null && rightValue === null) {
          comparison = 0
          break
        }
        if (leftValue === null) {
          return 1
        }
        if (rightValue === null) {
          return -1
        }
        comparison = leftValue - rightValue
        break
      }
    }

    if (comparison === 0) {
      comparison = compareText(left.mapName, right.mapName)
    }

    return sort.direction === "asc" ? comparison : -comparison
  })
}

function ProfileUnfinishedTableSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-12 rounded-2xl" />
      <div className="grid gap-4">
        {Array.from({ length: 1 }, (_, index) => (
          <div
            key={index}
            className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm"
          >
            <div className="space-y-3 p-6">
              <Skeleton className="h-6 w-32" />
              {Array.from({ length: 4 }, (_, rowIndex) => (
                <Skeleton key={rowIndex} className="h-12 w-full" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SortableHeader({
  column,
  label,
  sort,
  onSortChange,
  className,
}: {
  column: ProfileUnfinishedSortColumn
  label: string
  sort: ProfileUnfinishedSortState
  onSortChange: (column: ProfileUnfinishedSortColumn) => void
  className?: string
}) {
  const isActive = sort.column === column
  const direction = isActive ? sort.direction : null

  return (
    <Button
      type="button"
      variant="ghost"
      className={`-ml-3 h-8 px-3 text-left ${className ?? ""}`}
      onClick={() => onSortChange(column)}
    >
      <span>{label}</span>
      {direction === "asc" ? (
        <ArrowUp className="ml-2 size-4" />
      ) : direction === "desc" ? (
        <ArrowDown className="ml-2 size-4" />
      ) : null}
    </Button>
  )
}

const UnfinishedColumn = memo(function UnfinishedColumn({
  emptyMessage,
  hasMore,
  loadMoreRef,
  rows,
  sort,
  title,
  type,
  onSortChange,
  mapMenu,
}: {
  emptyMessage: string
  hasMore: boolean
  loadMoreRef: React.RefObject<HTMLDivElement | null>
  rows: ProfileUnfinishedRow[]
  sort: ProfileUnfinishedSortState
  title: string
  type: ProfileUnfinishedType
  onSortChange: (column: ProfileUnfinishedSortColumn) => void
  mapMenu: (mapId: number) => ReactNode
}) {
  const { t } = useTranslation()
  const finisherMetric = type === "NUB" ? "nubFinishers" : "proFinishers"
  return (
    <section
      aria-label={t("profile.unfinished.ariaLabel", { type: title })}
      className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm"
      data-testid={`profile-unfinished-column-${type.toLowerCase()}`}
    >
      <div className="overflow-x-auto">
        <Table className="[&_td]:px-3 [&_th]:px-3">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="min-w-48 normal-case tracking-normal text-foreground/80">
                <SortableHeader
                  column="map"
                  label={t("labels.map")}
                  sort={sort}
                  onSortChange={onSortChange}
                  className="normal-case tracking-normal text-foreground/80"
                />
              </TableHead>
              <TableHead className="min-w-16 normal-case tracking-normal text-foreground/80">
                <SortableHeader
                  column="tier"
                  label={t("labels.tier")}
                  sort={sort}
                  onSortChange={onSortChange}
                  className="normal-case tracking-normal text-foreground/80"
                />
              </TableHead>
              <TableHead className="min-w-28 text-right normal-case tracking-normal text-foreground/80">
                <SortableHeader
                  column="wrTime"
                  label={t("labels.wrTime")}
                  sort={sort}
                  onSortChange={onSortChange}
                  className="justify-end normal-case tracking-normal text-foreground/80"
                />
              </TableHead>
              {(
                [
                  type === "NUB"
                    ? (["nubFinishers", "maps.nubFinishers"] as const)
                    : (["proFinishers", "maps.proFinishers"] as const),
                  ["firstMedian", "profile.unfinished.firstMedian"],
                  ["medianPbTime", "maps.overview.medianPbTime"],
                  ["overallRating", "labels.rating"],
                  ["createdAt", "maps.filterFields.createdAt"],
                ] as const
              ).map(([column, label]) => (
                <TableHead
                  key={column}
                  className="min-w-28 text-right normal-case tracking-normal text-foreground/80"
                >
                  <SortableHeader
                    column={column}
                    label={t(label)}
                    sort={sort}
                    onSortChange={onSortChange}
                    className="justify-end normal-case tracking-normal text-foreground/80"
                  />
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length > 0 ? (
              rows.map((row) => (
                <TableRow
                  key={row.mapId}
                  data-testid={`profile-unfinished-${type.toLowerCase()}-row-${row.mapId}`}
                >
                  <TableCell>
                    <MapDisplay
                      mapName={row.mapName}
                      mapId={row.mapId}
                      containerClassName="block"
                      playerMenuItems={mapMenu(row.mapId)}
                    />
                  </TableCell>
                  <TableCell>
                    <TierBadge tier={row.tier} />
                  </TableCell>
                  <TableCell className="text-right font-mono font-medium">
                    {row.wrTime === null ? "-" : formatRecordTime(row.wrTime)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {row[finisherMetric] === null
                      ? "—"
                      : formatNumber(row[finisherMetric])}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {row.firstMedian === null
                      ? "—"
                      : formatRecordTime(row.firstMedian)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {row.medianPbTime === null
                      ? "—"
                      : formatRecordTime(row.medianPbTime)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <div className="flex min-w-44 justify-end">
                      <ReviewSummaryRow
                        value={row.overallRating}
                        count={row.reviewsCount}
                      />
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <FormattedDateTime
                      value={
                        row.createdAt === null ? null : new Date(row.createdAt)
                      }
                      dateOnly
                      fallback="—"
                    />
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className="h-32 text-center text-muted-foreground"
                >
                  {emptyMessage}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      {hasMore ? (
        <div
          ref={loadMoreRef}
          className="flex h-14 items-center justify-center text-sm text-muted-foreground"
        >
          {t("profile.unfinished.loadMore")}
        </div>
      ) : null}
    </section>
  )
})

export function ProfileUnfinishedTab({
  isOwnProfile,
  isProOnly,
  maps,
  mapsError,
  mapsLoading,
  nubRecords,
  nubRecordsError,
  nubRecordsLoading,
  onIsProOnlyChange,
  proRecords,
  proRecordsError,
  proRecordsLoading,
  useWrBasedProCompletion,
}: {
  isOwnProfile: boolean
  isProOnly: boolean
  maps: MapPublic[]
  mapsError: boolean
  mapsLoading: boolean
  nubRecords: RecordPublic[]
  nubRecordsError: boolean
  nubRecordsLoading: boolean
  onIsProOnlyChange: (checked: boolean) => void
  proRecords: RecordPublic[]
  proRecordsError: boolean
  proRecordsLoading: boolean
  useWrBasedProCompletion: boolean
}) {
  const { t } = useTranslation()
  const { scope } = useScope()
  const hiddenMaps = useHiddenMaps(isOwnProfile)
  const { showHiddenMaps: showHidden } = useGlobalPreferences()
  const visibleMaps = useMemo(
    () => maps.filter((map) => showHidden || !hiddenMaps.ids.has(map.id)),
    [maps, showHidden, hiddenMaps.ids],
  )
  const [initialView] = useState(unfinishedView)
  const [mapSearch, setMapSearch] = useState(initialView?.mapSearch ?? "")
  const [selectedTier, setSelectedTier] = useState<TierSelectorValue>(
    initialView?.selectedTier ?? "all",
  )
  const [nubVisibleCount, setNubVisibleCount] = useState(
    PROFILE_UNFINISHED_PAGE_SIZE,
  )
  const [proVisibleCount, setProVisibleCount] = useState(
    PROFILE_UNFINISHED_PAGE_SIZE,
  )
  const [nubSort, setNubSort] = useState<ProfileUnfinishedSortState>(
    initialView?.nubSort ?? {
      column: "map",
      direction: "asc",
    },
  )
  const [proSort, setProSort] = useState<ProfileUnfinishedSortState>(
    initialView?.proSort ?? {
      column: "map",
      direction: "asc",
    },
  )
  const deferredMapSearch = useDeferredValue(mapSearch)
  const currentView = useRef({
    mapSearch,
    selectedTier,
    nubSort,
    proSort,
    isProOnly,
  })
  useEffect(() => {
    currentView.current = {
      mapSearch,
      selectedTier,
      nubSort,
      proSort,
      isProOnly,
    }
  }, [mapSearch, selectedTier, nubSort, proSort, isProOnly])
  useEffect(() => {
    if (initialView) onIsProOnlyChange(initialView.isProOnly)
    return () => {
      unfinishedView = currentView.current
    }
  }, [initialView, onIsProOnlyChange])
  const nubLoadMoreRef = useRef<HTMLDivElement | null>(null)
  const proLoadMoreRef = useRef<HTMLDivElement | null>(null)
  const nubWrsQuery = useQuery(
    getProfileMapWrsQueryOptions({
      scope,
      isProOnly: false,
    }),
  )
  const proWrsQuery = useQuery(
    getProfileMapWrsQueryOptions({
      scope,
      isProOnly: true,
    }),
  )

  const metricsQuery = useQuery({
    queryKey: ["leaderboards", "maps", "catalog", scope],
    queryFn: () => LeaderboardsService.readMapLeaderboard({ scope }),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  })
  const metricsByMapId = useMemo(
    () =>
      new Map(metricsQuery.data?.data.map((entry) => [entry.map.id, entry])),
    [metricsQuery.data],
  )
  const mapsByMapId = useMemo(
    () => new Map(maps.map((map) => [map.id, map])),
    [maps],
  )
  const addMetrics = useCallback(
    (row: BaseUnfinishedRow): ProfileUnfinishedRow => {
      const metrics = metricsByMapId.get(row.mapId)
      const map = mapsByMapId.get(row.mapId)
      const review = map?.review_summary
      return {
        ...row,
        overallRating: review?.reviews_count ? review.overall_adjusted : null,
        reviewsCount: review?.reviews_count ?? 0,
        nubFinishers: metrics?.unique_nub_finishes ?? null,
        proFinishers: metrics?.unique_pro_finishes ?? null,
        createdAt: map ? Date.parse(map.created_on) : null,
        medianPbTime:
          metrics && metrics.median_first_completion_time > 0
            ? metrics.median_first_completion_time
            : null,
        firstMedian:
          metrics?.median_first_finish_time != null &&
          metrics.median_first_finish_time > 0
            ? metrics.median_first_finish_time
            : null,
      }
    },
    [metricsByMapId, mapsByMapId],
  )

  const normalizedMapSearch = deferredMapSearch.trim().toLocaleLowerCase()
  const selectedTierNumber =
    selectedTier === "all" ? null : Number(selectedTier)

  const nubRows = useMemo(() => {
    return buildProfileUnfinishedRows({
      maps: visibleMaps,
      records: nubRecords,
      wrs: nubWrsQuery.data ?? [],
      scope,
    }).filter((row) => {
      if (
        normalizedMapSearch.length > 0 &&
        !row.mapName.toLocaleLowerCase().includes(normalizedMapSearch)
      ) {
        return false
      }

      if (selectedTierNumber !== null && row.tier !== selectedTierNumber) {
        return false
      }

      return true
    })
  }, [
    visibleMaps,
    nubRecords,
    nubWrsQuery.data,
    normalizedMapSearch,
    scope,
    selectedTierNumber,
  ])

  const proRows = useMemo(() => {
    return buildProfileUnfinishedRows({
      maps: visibleMaps,
      records: proRecords,
      wrs: proWrsQuery.data ?? [],
      scope,
      requireWrAvailability: useWrBasedProCompletion,
    }).filter((row) => {
      if (
        normalizedMapSearch.length > 0 &&
        !row.mapName.toLocaleLowerCase().includes(normalizedMapSearch)
      ) {
        return false
      }

      if (selectedTierNumber !== null && row.tier !== selectedTierNumber) {
        return false
      }

      return true
    })
  }, [
    visibleMaps,
    proRecords,
    proWrsQuery.data,
    normalizedMapSearch,
    scope,
    selectedTierNumber,
    useWrBasedProCompletion,
  ])

  const sortedNubRows = useMemo(() => {
    return sortProfileUnfinishedRows(nubRows.map(addMetrics), nubSort)
  }, [nubRows, nubSort, addMetrics])

  const sortedProRows = useMemo(() => {
    return sortProfileUnfinishedRows(proRows.map(addMetrics), proSort)
  }, [proRows, proSort, addMetrics])

  const visibleNubRows = useMemo(() => {
    return sortedNubRows.slice(0, nubVisibleCount)
  }, [nubVisibleCount, sortedNubRows])

  const visibleProRows = useMemo(() => {
    return sortedProRows.slice(0, proVisibleCount)
  }, [proVisibleCount, sortedProRows])

  useEffect(() => {
    setNubVisibleCount(
      Math.min(PROFILE_UNFINISHED_PAGE_SIZE, sortedNubRows.length),
    )
    setProVisibleCount(
      Math.min(PROFILE_UNFINISHED_PAGE_SIZE, sortedProRows.length),
    )
  }, [sortedNubRows.length, sortedProRows.length])

  useEffect(() => {
    const target = nubLoadMoreRef.current
    if (isProOnly || !target || nubVisibleCount >= sortedNubRows.length) {
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (!entry?.isIntersecting) {
          return
        }

        setNubVisibleCount((current) =>
          Math.min(
            current + PROFILE_UNFINISHED_PAGE_SIZE,
            sortedNubRows.length,
          ),
        )
      },
      {
        rootMargin: "320px 0px",
      },
    )

    observer.observe(target)
    return () => observer.disconnect()
  }, [nubVisibleCount, sortedNubRows.length, isProOnly])

  useEffect(() => {
    const target = proLoadMoreRef.current
    if (!isProOnly || !target || proVisibleCount >= sortedProRows.length) {
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (!entry?.isIntersecting) {
          return
        }

        setProVisibleCount((current) =>
          Math.min(
            current + PROFILE_UNFINISHED_PAGE_SIZE,
            sortedProRows.length,
          ),
        )
      },
      {
        rootMargin: "320px 0px",
      },
    )

    observer.observe(target)
    return () => observer.disconnect()
  }, [proVisibleCount, sortedProRows.length, isProOnly])

  const handleNubSortChange = useCallback(
    (column: ProfileUnfinishedSortColumn) => {
      setNubSort((current) => {
        if (current.column === column) {
          return {
            column,
            direction: current.direction === "asc" ? "desc" : "asc",
          }
        }

        return {
          column,
          direction: column === "map" ? "asc" : "desc",
        }
      })
    },
    [],
  )

  const handleProSortChange = useCallback(
    (column: ProfileUnfinishedSortColumn) => {
      setProSort((current) => {
        if (current.column === column) {
          return {
            column,
            direction: current.direction === "asc" ? "desc" : "asc",
          }
        }

        return {
          column,
          direction: column === "map" ? "asc" : "desc",
        }
      })
    },
    [],
  )

  if (
    mapsError ||
    nubRecordsError ||
    proRecordsError ||
    nubWrsQuery.isError ||
    proWrsQuery.isError
  ) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {t("profile.unfinished.loadFailed")}{" "}
          {t("profile.unfinished.loadFailedBody")}
        </AlertDescription>
      </Alert>
    )
  }

  if (
    mapsLoading ||
    nubRecordsLoading ||
    proRecordsLoading ||
    nubWrsQuery.isLoading ||
    proWrsQuery.isLoading
  ) {
    return <ProfileUnfinishedTableSkeleton />
  }

  if (hiddenMaps.loading || hiddenMaps.error) return null
  const nubEmptyMessage = t("profile.unfinished.emptyNub")
  const proEmptyMessage = t("profile.unfinished.emptyPro")

  const selectedType: ProfileUnfinishedType = isProOnly ? "PRO" : "NUB"
  const selectedTitle = isProOnly
    ? t("profile.unfinished.typePro")
    : t("profile.unfinished.typeNub")
  const selectedEmptyMessage = isProOnly ? proEmptyMessage : nubEmptyMessage
  const selectedSort = isProOnly ? proSort : nubSort

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-card/60 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
          <Input
            aria-label={t("profile.unfinished.mapSearchAria")}
            value={mapSearch}
            onChange={(event) => setMapSearch(event.target.value)}
            placeholder={t("profile.unfinished.mapSearchPlaceholder")}
            className="h-9 w-full border-border/70 bg-[#f5f5f4] text-sm font-normal dark:bg-background/80 sm:max-w-xs"
          />
          <TierSelector
            value={selectedTier}
            onValueChange={setSelectedTier}
            triggerClassName="w-auto"
            showAllLabelInTrigger
            ariaLabel={t("profile.unfinished.filterTierAria")}
          />
        </div>
        <output className="text-sm text-muted-foreground">
          {t("profile.unfinished.mapsCount", {
            count: isProOnly ? sortedProRows.length : sortedNubRows.length,
          })}
        </output>
        <RecordTypeTabs
          id="profile-unfinished-pro-only"
          isProOnly={isProOnly}
          onCheckedChange={onIsProOnlyChange}
        />
      </div>
      {metricsQuery.isError ? (
        <Alert>
          <AlertDescription>
            {t("maps.overview.metricsUnavailable")}
          </AlertDescription>
        </Alert>
      ) : null}
      <UnfinishedColumn
        mapMenu={hiddenMaps.menuItem}
        emptyMessage={selectedEmptyMessage}
        hasMore={
          selectedType === "NUB"
            ? visibleNubRows.length < sortedNubRows.length
            : visibleProRows.length < sortedProRows.length
        }
        loadMoreRef={selectedType === "NUB" ? nubLoadMoreRef : proLoadMoreRef}
        rows={selectedType === "NUB" ? visibleNubRows : visibleProRows}
        sort={selectedSort}
        title={selectedTitle}
        type={selectedType}
        onSortChange={
          selectedType === "NUB" ? handleNubSortChange : handleProSortChange
        }
      />
    </div>
  )
}
