import { useQuery } from "@tanstack/react-query"
import { ArrowDown, ArrowUp } from "lucide-react"
import {
  memo,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"

import type { MapPublic, RecordPublic } from "@/client"
import { MapDisplay } from "@/components/Common/MapDisplay"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { formatRecordTime } from "@/components/Records/utils"
import { TierBadge } from "@/components/Servers/TierBadge"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import {
  buildProfileUnfinishedRows,
  getProfileUnfinishedMapWrsQueryOptions,
  type ProfileUnfinishedRow,
} from "./profile-utils"

const UNFINISHED_SPLIT_MIN_VIEWPORT_WIDTH = 1280
const PROFILE_UNFINISHED_PAGE_SIZE = 100

type ProfileUnfinishedType = "NUB" | "PRO"
type ProfileUnfinishedSortColumn = "map" | "tier" | "wrTime"
type ProfileUnfinishedSortDirection = "asc" | "desc"

type ProfileUnfinishedSortState = {
  column: ProfileUnfinishedSortColumn
  direction: ProfileUnfinishedSortDirection
}

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
      case "wrTime": {
        if (left.wrTime === null && right.wrTime === null) {
          comparison = 0
          break
        }
        if (left.wrTime === null) {
          return 1
        }
        if (right.wrTime === null) {
          return -1
        }
        comparison = left.wrTime - right.wrTime
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
      <div className="grid gap-4 xl:grid-cols-2">
        {Array.from({ length: 2 }, (_, index) => (
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
}: {
  emptyMessage: string
  hasMore: boolean
  loadMoreRef: React.RefObject<HTMLDivElement | null>
  rows: ProfileUnfinishedRow[]
  sort: ProfileUnfinishedSortState
  title: string
  type: ProfileUnfinishedType
  onSortChange: (column: ProfileUnfinishedSortColumn) => void
}) {
  return (
    <section
      aria-label={`${title} unfinished`}
      className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm"
      data-testid={`profile-unfinished-column-${type.toLowerCase()}`}
    >
      <div className="border-b border-border/60 px-5 py-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold tracking-[0.12em] text-foreground uppercase">
            {title}
          </h3>
          <span className="text-xs text-muted-foreground">
            {rows.length} maps
          </span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="min-w-60 normal-case tracking-normal text-foreground/80">
                <SortableHeader
                  column="map"
                  label="Map"
                  sort={sort}
                  onSortChange={onSortChange}
                  className="normal-case tracking-normal text-foreground/80"
                />
              </TableHead>
              <TableHead className="min-w-16 normal-case tracking-normal text-foreground/80">
                <SortableHeader
                  column="tier"
                  label="Tier"
                  sort={sort}
                  onSortChange={onSortChange}
                  className="normal-case tracking-normal text-foreground/80"
                />
              </TableHead>
              <TableHead className="min-w-28 text-right normal-case tracking-normal text-foreground/80">
                <SortableHeader
                  column="wrTime"
                  label="WR Time"
                  sort={sort}
                  onSortChange={onSortChange}
                  className="justify-end normal-case tracking-normal text-foreground/80"
                />
              </TableHead>
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
                    <MapDisplay mapName={row.mapName} />
                  </TableCell>
                  <TableCell>
                    <TierBadge tier={row.tier} />
                  </TableCell>
                  <TableCell className="text-right font-mono font-medium">
                    {row.wrTime === null ? "-" : formatRecordTime(row.wrTime)}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={3}
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
          Loading more maps...
        </div>
      ) : null}
    </section>
  )
})

export function ProfileUnfinishedTab({
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
}: {
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
}) {
  const { scope } = useScope()
  const [isSplitLayout, setIsSplitLayout] = useState(false)
  const [mapSearch, setMapSearch] = useState("")
  const [selectedTier, setSelectedTier] = useState<TierSelectorValue>("all")
  const [nubVisibleCount, setNubVisibleCount] = useState(
    PROFILE_UNFINISHED_PAGE_SIZE,
  )
  const [proVisibleCount, setProVisibleCount] = useState(
    PROFILE_UNFINISHED_PAGE_SIZE,
  )
  const [nubSort, setNubSort] = useState<ProfileUnfinishedSortState>({
    column: "map",
    direction: "asc",
  })
  const [proSort, setProSort] = useState<ProfileUnfinishedSortState>({
    column: "map",
    direction: "asc",
  })
  const deferredMapSearch = useDeferredValue(mapSearch)
  const nubLoadMoreRef = useRef<HTMLDivElement | null>(null)
  const proLoadMoreRef = useRef<HTMLDivElement | null>(null)
  const nubWrsQuery = useQuery(
    getProfileUnfinishedMapWrsQueryOptions({
      scope,
      isProOnly: false,
    }),
  )
  const proWrsQuery = useQuery(
    getProfileUnfinishedMapWrsQueryOptions({
      scope,
      isProOnly: true,
    }),
  )

  useEffect(() => {
    const updateLayout = () => {
      setIsSplitLayout(window.innerWidth >= UNFINISHED_SPLIT_MIN_VIEWPORT_WIDTH)
    }

    updateLayout()

    window.addEventListener("resize", updateLayout)

    return () => window.removeEventListener("resize", updateLayout)
  }, [])

  const normalizedMapSearch = deferredMapSearch.trim().toLocaleLowerCase()
  const selectedTierNumber =
    selectedTier === "all" ? null : Number(selectedTier)

  const nubRows = useMemo(() => {
    return buildProfileUnfinishedRows({
      maps,
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
    maps,
    nubRecords,
    nubWrsQuery.data,
    normalizedMapSearch,
    scope,
    selectedTierNumber,
  ])

  const proRows = useMemo(() => {
    return buildProfileUnfinishedRows({
      maps,
      records: proRecords,
      wrs: proWrsQuery.data ?? [],
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
    maps,
    proRecords,
    proWrsQuery.data,
    normalizedMapSearch,
    scope,
    selectedTierNumber,
  ])

  const sortedNubRows = useMemo(() => {
    return sortProfileUnfinishedRows(nubRows, nubSort)
  }, [nubRows, nubSort])

  const sortedProRows = useMemo(() => {
    return sortProfileUnfinishedRows(proRows, proSort)
  }, [proRows, proSort])

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
    if (!target || nubVisibleCount >= sortedNubRows.length) {
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
  }, [nubVisibleCount, sortedNubRows.length])

  useEffect(() => {
    const target = proLoadMoreRef.current
    if (!target || proVisibleCount >= sortedProRows.length) {
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
  }, [proVisibleCount, sortedProRows.length])

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
          Failed to load unfinished maps. Reload the page and try again.
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

  const nubEmptyMessage =
    "No unfinished maps found for this player in the selected scope."
  const proEmptyMessage =
    "No unfinished pro maps found for this player in the selected scope."

  const selectedType: ProfileUnfinishedType = isProOnly ? "PRO" : "NUB"
  const selectedTitle = isProOnly ? "PRO" : "NUB"
  const selectedEmptyMessage = isProOnly ? proEmptyMessage : nubEmptyMessage
  const selectedSort = isProOnly ? proSort : nubSort

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-card/60 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
          <Input
            aria-label="Search unfinished map name"
            value={mapSearch}
            onChange={(event) => setMapSearch(event.target.value)}
            placeholder="Search map"
            className="h-9 w-full border-border/70 bg-background/80 text-sm font-normal sm:max-w-xs"
          />
          <TierSelector
            value={selectedTier}
            onValueChange={setSelectedTier}
            allLabel="Tier"
            triggerClassName="h-9 w-full justify-between border-border/70 bg-background/80 px-3 text-sm sm:w-32"
            ariaLabel="Filter unfinished maps by tier"
          />
        </div>
        {!isSplitLayout ? (
          <Label
            htmlFor="profile-unfinished-pro-only"
            className="flex h-9 w-fit items-center justify-start gap-2 rounded-lg border border-border/70 bg-background/80 px-3 text-[11px] font-medium tracking-[0.08em] text-foreground/80 uppercase"
          >
            <Switch
              id="profile-unfinished-pro-only"
              checked={isProOnly}
              onCheckedChange={onIsProOnlyChange}
              className="data-[state=unchecked]:bg-[#f3c40f] data-[state=unchecked]:shadow-[#f3c40f]/35 data-[state=checked]:bg-[#3598db] data-[state=checked]:shadow-[#3598db]/35 dark:data-[state=checked]:bg-[#3598db]"
            />
            <span>{isProOnly ? "Pro" : "Nub"}</span>
          </Label>
        ) : null}
      </div>

      {isSplitLayout ? (
        <div className="grid grid-cols-2 gap-4">
          <UnfinishedColumn
            emptyMessage={nubEmptyMessage}
            hasMore={visibleNubRows.length < sortedNubRows.length}
            loadMoreRef={nubLoadMoreRef}
            rows={visibleNubRows}
            sort={nubSort}
            title="NUB"
            type="NUB"
            onSortChange={handleNubSortChange}
          />
          <UnfinishedColumn
            emptyMessage={proEmptyMessage}
            hasMore={visibleProRows.length < sortedProRows.length}
            loadMoreRef={proLoadMoreRef}
            rows={visibleProRows}
            sort={proSort}
            title="PRO"
            type="PRO"
            onSortChange={handleProSortChange}
          />
        </div>
      ) : (
        <UnfinishedColumn
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
      )}
    </div>
  )
}
