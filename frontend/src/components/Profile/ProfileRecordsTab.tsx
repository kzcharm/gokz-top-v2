import { useQuery } from "@tanstack/react-query"
import { Pin, PinOff } from "lucide-react"
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"

import {
  ModeSelector,
  type ModeSelectorValue,
} from "@/components/Common/ModeSelector"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { normalizeRecordMode } from "@/components/Records/mode"
import { PbRecordsTable } from "@/components/Records/PbRecordsTable"
import {
  type PbRecordsColumn,
  type PbRecordsSortState,
  sortPbRecords,
} from "@/components/Records/pb-records-utils"
import type { RecordPublic } from "@/client"
import { normalizeTierValue } from "@/components/Servers/tier"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  getProfilePbRecordsQueryOptions,
  getProfilePinnedRecordKey,
} from "./profile-utils"

const PROFILE_RECORDS_PAGE_SIZE = 50

function ProfileRecordsTableSkeleton() {
  return (
    <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm">
      <div className="space-y-3 p-6">
        <Skeleton className="h-6 w-56" />
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-12 w-full" />
        ))}
      </div>
    </div>
  )
}

export function ProfileRecordsTab({
  steamid64,
  canManagePinnedRecords,
  pinnedRecordKeys,
  pinnedRecordsMutating,
  onPinRecord,
  onUnpinRecord,
}: {
  steamid64: string
  canManagePinnedRecords: boolean
  pinnedRecordKeys: Set<string>
  pinnedRecordsMutating: boolean
  onPinRecord: (mapId: number, type: "NUB" | "PRO") => void
  onUnpinRecord: (mapId: number, type: "NUB" | "PRO") => void
}) {
  const { scope } = useScope()
  const [isProOnly, setIsProOnly] = useState(false)
  const [mapSearch, setMapSearch] = useState("")
  const [selectedMode, setSelectedMode] = useState<ModeSelectorValue>("all")
  const [selectedTier, setSelectedTier] = useState<TierSelectorValue>("all")
  const [maxPoints, setMaxPoints] = useState("")
  const [serverSearch, setServerSearch] = useState("")
  const [sort, setSort] = useState<PbRecordsSortState>({
    column: "datetime",
    direction: "desc",
  })
  const [visibleCount, setVisibleCount] = useState(PROFILE_RECORDS_PAGE_SIZE)
  const loadMoreRef = useRef<HTMLDivElement | null>(null)
  const deferredMapSearch = useDeferredValue(mapSearch)
  const deferredServerSearch = useDeferredValue(serverSearch)

  const recordsQuery = useQuery({
    ...getProfilePbRecordsQueryOptions({
      steamid64,
      scope,
      isProOnly,
    }),
  })

  const sortedRecords = useMemo(() => {
    const normalizedMapSearch = deferredMapSearch.trim().toLocaleLowerCase()
    const normalizedServerSearch = deferredServerSearch
      .trim()
      .toLocaleLowerCase()
    const parsedMaxPoints = maxPoints.trim() === "" ? null : Number(maxPoints)

    const filteredRecords = (recordsQuery.data ?? []).filter((record) => {
      if (
        normalizedMapSearch.length > 0 &&
        !record.map_name.toLocaleLowerCase().includes(normalizedMapSearch)
      ) {
        return false
      }

      if (
        normalizedServerSearch.length > 0 &&
        !record.server_name.toLocaleLowerCase().includes(normalizedServerSearch)
      ) {
        return false
      }

      if (
        selectedMode !== "all" &&
        normalizeRecordMode(record.mode) !== selectedMode
      ) {
        return false
      }

      if (selectedTier !== "all") {
        const normalizedTier = normalizeTierValue(record.map_tier)
        if (normalizedTier !== Number(selectedTier)) {
          return false
        }
      }

      if (parsedMaxPoints !== null && Number.isFinite(parsedMaxPoints)) {
        if (record.points > parsedMaxPoints) {
          return false
        }
      }

      return true
    })

    return sortPbRecords(filteredRecords, sort)
  }, [
    deferredMapSearch,
    deferredServerSearch,
    maxPoints,
    recordsQuery.data,
    selectedMode,
    selectedTier,
    sort,
  ])

  const visibleRecords = useMemo(() => {
    return sortedRecords.slice(0, visibleCount)
  }, [sortedRecords, visibleCount])

  useEffect(() => {
    setVisibleCount(PROFILE_RECORDS_PAGE_SIZE)
  }, [])

  useEffect(() => {
    const target = loadMoreRef.current
    if (!target || visibleCount >= sortedRecords.length) {
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (!entry?.isIntersecting) {
          return
        }

        startTransition(() => {
          setVisibleCount((current) =>
            Math.min(current + PROFILE_RECORDS_PAGE_SIZE, sortedRecords.length),
          )
        })
      },
      {
        rootMargin: "320px 0px",
      },
    )

    observer.observe(target)
    return () => observer.disconnect()
  }, [sortedRecords.length, visibleCount])

  const handleSortChange = (column: PbRecordsColumn) => {
    setSort((current) => {
      if (current.column === column) {
        return {
          column,
          direction: current.direction === "desc" ? "asc" : "desc",
        }
      }

      return {
        column,
        direction: "desc",
      }
    })
  }

  const filterEmptyMessage = isProOnly
    ? "No stage 0 pro records found for this player with the current filters."
    : "No stage 0 records found for this player with the current filters."

  const hasActiveClientFilters =
    deferredMapSearch.trim().length > 0 ||
    deferredServerSearch.trim().length > 0 ||
    selectedMode !== "all" ||
    selectedTier !== "all" ||
    maxPoints.trim().length > 0

  const emptyMessage = hasActiveClientFilters
    ? filterEmptyMessage
    : isProOnly
      ? "No stage 0 pro records found for this player in the selected scope."
      : "No stage 0 records found for this player in the selected scope."

  const pointInputClassName =
    "h-8 min-w-0 rounded-md border-border/70 bg-background/80 text-xs font-normal"
  const recordType = isProOnly ? "PRO" : "NUB"
  const getRowContextMenu = (record: RecordPublic) => {
    if (!canManagePinnedRecords) {
      return null
    }

    const isPinned = pinnedRecordKeys.has(
      getProfilePinnedRecordKey({
        mapId: record.map_id,
        type: recordType,
      }),
    )

    return (
      <DropdownMenuItem
        disabled={pinnedRecordsMutating}
        onSelect={(event) => {
          event.preventDefault()
          if (isPinned) {
            onUnpinRecord(record.map_id, recordType)
            return
          }
          onPinRecord(record.map_id, recordType)
        }}
      >
        {isPinned ? <PinOff /> : <Pin />}
        {isPinned ? "Unpin this record" : "Pin this record"}
      </DropdownMenuItem>
    )
  }

  return (
    <div className="space-y-4">
      {recordsQuery.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load profile records. Reload the page and try again.
          </AlertDescription>
        </Alert>
      ) : null}

      {recordsQuery.isLoading ? (
        <ProfileRecordsTableSkeleton />
      ) : (
        <div className="space-y-4">
          <PbRecordsTable
            records={visibleRecords}
            columns={[
              "map",
              "mode",
              "tier",
              "tps",
              "time",
              "points",
              "server",
              "datetime",
            ]}
            columnFilters={{
              map: (
                <Input
                  aria-label="Search map name"
                  value={mapSearch}
                  onChange={(event) => setMapSearch(event.target.value)}
                  placeholder="Search map"
                  className="h-8 w-56 border-border/70 bg-background/80 text-xs font-normal"
                />
              ),
              mode: (
                <ModeSelector
                  value={selectedMode}
                  onValueChange={setSelectedMode}
                  allLabel="Modes"
                  triggerClassName="h-8 border-border/70 bg-background/80 text-xs"
                  ariaLabel="Filter by mode"
                />
              ),
              tier: (
                <TierSelector
                  value={selectedTier}
                  onValueChange={setSelectedTier}
                  allLabel="Tier"
                  triggerClassName="h-8 border-border/70 bg-background/80 text-xs"
                  ariaLabel="Filter by tier"
                />
              ),
              tps: (
                <Label
                  htmlFor="profile-records-pro-only"
                  className="flex h-8 items-center justify-start gap-2 rounded-md border border-border/70 bg-background/80 px-2 text-[11px] font-medium tracking-[0.08em] text-foreground/80 uppercase"
                >
                  <Switch
                    id="profile-records-pro-only"
                    checked={isProOnly}
                    onCheckedChange={setIsProOnly}
                    className="data-[state=checked]:bg-[#3598db] data-[state=checked]:shadow-[#3598db]/35 dark:data-[state=checked]:bg-[#3598db]"
                  />
                  <span>Pro</span>
                </Label>
              ),
              points: (
                <Input
                  aria-label="Maximum points"
                  value={maxPoints}
                  onChange={(event) => setMaxPoints(event.target.value)}
                  placeholder="Max"
                  inputMode="decimal"
                  className={`${pointInputClassName} w-[4.25rem]`}
                />
              ),
              server: (
                <Input
                  aria-label="Search server"
                  value={serverSearch}
                  onChange={(event) => setServerSearch(event.target.value)}
                  placeholder="Search server"
                  className="h-8 border-border/70 bg-background/80 text-xs font-normal"
                />
              ),
            }}
            emptyMessage={emptyMessage}
            dateTimeDisplay="contextual-relative"
            sort={sort}
            onSortChange={handleSortChange}
            getRowContextMenu={getRowContextMenu}
          />
          {visibleCount < sortedRecords.length ? (
            <div
              ref={loadMoreRef}
              className="flex h-14 items-center justify-center text-sm text-muted-foreground"
            >
              Loading more records...
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
