import { useQuery } from "@tanstack/react-query"
import { ChevronDownIcon, Pin, PinOff } from "lucide-react"
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import type { RecordPublic } from "@/client"
import {
  useAdminMode,
  useAdminModeSurface,
} from "@/components/admin-mode-provider"
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
import { RecordRunHistoryDialog } from "@/components/Records/RecordRunHistoryDialog"
import { normalizeTierValue } from "@/components/Servers/tier"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import useAuth from "@/hooks/useAuth"
import { canModerateBansAndRecords } from "@/lib/user-roles"
import { cn } from "@/lib/utils"
import { RowContextMenuItem } from "../Common/RowContextMenu"
import {
  DeleteCourseRecordsButton,
  useRecordAdminActions,
} from "../Records/admin-actions"
import {
  getProfilePbRecordsQueryOptions,
  getProfilePinnedRecordKey,
} from "./profile-utils"

const PROFILE_RECORDS_PAGE_SIZE = 50
const POINTS_RANGE_MIN = 0
const POINTS_RANGE_MAX = 1000
const POINTS_RANGE_PRESETS = [
  { label: "0 ~ 799", min: 0, max: 799 },
  { label: "800 ~ 899", min: 800, max: 899 },
  { label: "900 ~ 1000", min: 900, max: 1000 },
] as const

function parsePointsBound(value: string, fallback: number) {
  const trimmedValue = value.trim()
  if (trimmedValue.length === 0) {
    return fallback
  }

  const parsedValue = Number(trimmedValue)
  if (!Number.isFinite(parsedValue)) {
    return fallback
  }

  return Math.max(
    POINTS_RANGE_MIN,
    Math.min(POINTS_RANGE_MAX, Math.round(parsedValue)),
  )
}

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

function PointsRangeFilter({
  minPoints,
  maxPoints,
  onMinPointsChange,
  onMaxPointsChange,
}: {
  minPoints: string
  maxPoints: string
  onMinPointsChange: (value: string) => void
  onMaxPointsChange: (value: string) => void
}) {
  const effectiveMinPoints = parsePointsBound(minPoints, POINTS_RANGE_MIN)
  const effectiveMaxPoints = parsePointsBound(maxPoints, POINTS_RANGE_MAX)
  const trimmedMinPoints = minPoints.trim()
  const trimmedMaxPoints = maxPoints.trim()
  const hasActiveRange =
    trimmedMinPoints.length > 0 || trimmedMaxPoints.length > 0
  const rangeLabel = hasActiveRange
    ? `${effectiveMinPoints} ~ ${effectiveMaxPoints}`
    : null
  const updateRange = (nextMin: number, nextMax: number) => {
    const clampedMin = Math.max(
      POINTS_RANGE_MIN,
      Math.min(POINTS_RANGE_MAX, Math.round(nextMin)),
    )
    const clampedMax = Math.max(
      clampedMin,
      Math.min(POINTS_RANGE_MAX, Math.round(nextMax)),
    )

    onMinPointsChange(clampedMin === POINTS_RANGE_MIN ? "" : String(clampedMin))
    onMaxPointsChange(clampedMax === POINTS_RANGE_MAX ? "" : String(clampedMax))
  }
  const triggerClassName =
    "flex h-8 min-w-11 items-center justify-center rounded-md border border-border/70 bg-background/80 px-1.5 text-[11px] font-medium shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
  const sliderClassName =
    "h-2 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary"

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Filter by points range"
          className={cn(
            triggerClassName,
            hasActiveRange ? "w-[6.75rem]" : "w-11",
            hasActiveRange && "border-primary/40 text-foreground",
          )}
        >
          <span className="flex items-center justify-center gap-1">
            {rangeLabel ? (
              <span className="truncate text-[10px] font-semibold tabular-nums">
                {rangeLabel}
              </span>
            ) : null}
            <ChevronDownIcon className="size-3.5 shrink-0 opacity-50" />
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className="w-52 space-y-3 p-3"
        onCloseAutoFocus={(event) => {
          event.preventDefault()
        }}
        onKeyDown={(event) => {
          event.stopPropagation()
        }}
      >
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            <span>Points</span>
            <span className="font-mono text-foreground">
              {effectiveMinPoints} ~ {effectiveMaxPoints}
            </span>
          </div>
          <div className="space-y-2">
            <div className="space-y-1">
              <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                <span>Min</span>
                <span className="font-mono text-foreground">
                  {effectiveMinPoints}
                </span>
              </div>
              <input
                type="range"
                min={POINTS_RANGE_MIN}
                max={effectiveMaxPoints}
                step={1}
                value={effectiveMinPoints}
                onChange={(event) => {
                  updateRange(Number(event.target.value), effectiveMaxPoints)
                }}
                className={sliderClassName}
                aria-label="Minimum points"
              />
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                <span>Max</span>
                <span className="font-mono text-foreground">
                  {effectiveMaxPoints}
                </span>
              </div>
              <input
                type="range"
                min={effectiveMinPoints}
                max={POINTS_RANGE_MAX}
                step={1}
                value={effectiveMaxPoints}
                onChange={(event) => {
                  updateRange(effectiveMinPoints, Number(event.target.value))
                }}
                className={sliderClassName}
                aria-label="Maximum points"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {POINTS_RANGE_PRESETS.map((preset) => (
              <Button
                key={preset.label}
                type="button"
                variant="outline"
                size="sm"
                className="h-7 px-2 text-[10px] font-semibold tabular-nums"
                onClick={() => {
                  updateRange(preset.min, preset.max)
                }}
              >
                {preset.label}
              </Button>
            ))}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-[10px]"
              onClick={() => {
                onMinPointsChange("")
                onMaxPointsChange("")
              }}
            >
              Reset
            </Button>
          </div>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function ProfileRecordsTab({
  steamid64,
  isProOnly,
  isBonus,
  canManagePinnedRecords,
  pinnedRecordKeys,
  pinnedRecordsMutating,
  onPinRecord,
  onUnpinRecord,
}: {
  steamid64: string
  isProOnly: boolean
  isBonus: boolean
  canManagePinnedRecords: boolean
  pinnedRecordKeys: Set<string>
  pinnedRecordsMutating: boolean
  onPinRecord: (mapId: number, type: "NUB" | "PRO") => void
  onUnpinRecord: (mapId: number, type: "NUB" | "PRO") => void
}) {
  const { enabled: adminModeEnabled } = useAdminMode()
  const { user } = useAuth()
  const { scope } = useScope()
  const { bulkDeleteMutation } = useRecordAdminActions()
  const [mapSearch, setMapSearch] = useState("")
  const [selectedMode, setSelectedMode] = useState<ModeSelectorValue>("all")
  const [selectedTier, setSelectedTier] = useState<TierSelectorValue>("all")
  const [selectedStage, setSelectedStage] = useState<number | null>(null)
  const [minPoints, setMinPoints] = useState("")
  const [maxPoints, setMaxPoints] = useState("")
  const [serverSearch, setServerSearch] = useState("")
  const [sort, setSort] = useState<PbRecordsSortState>({
    column: "datetime",
    direction: "desc",
  })
  const [historyRecord, setHistoryRecord] = useState<RecordPublic | null>(null)
  const [visibleCount, setVisibleCount] = useState(PROFILE_RECORDS_PAGE_SIZE)
  const loadMoreRef = useRef<HTMLDivElement | null>(null)
  const deferredMapSearch = useDeferredValue(mapSearch)
  const deferredServerSearch = useDeferredValue(serverSearch)
  const canUseRecordAdminActions =
    canManagePinnedRecords && canModerateBansAndRecords(user)
  useAdminModeSurface(canUseRecordAdminActions)
  const adminModeForRecords = adminModeEnabled && canUseRecordAdminActions

  const recordsQuery = useQuery({
    ...getProfilePbRecordsQueryOptions({
      identifier: steamid64,
      scope,
      isProOnly,
      isBonus,
      stage: selectedStage,
    }),
  })

  const sortedRecords = useMemo(() => {
    const normalizedMapSearch = deferredMapSearch.trim().toLocaleLowerCase()
    const normalizedServerSearch = deferredServerSearch
      .trim()
      .toLocaleLowerCase()
    const parsedMinPoints = minPoints.trim() === "" ? null : Number(minPoints)
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
        ![record.server_name, record.server_group?.name ?? ""].some(
          (serverLabel) =>
            serverLabel.toLocaleLowerCase().includes(normalizedServerSearch),
        )
      ) {
        return false
      }

      if (
        selectedMode !== "all" &&
        normalizeRecordMode(record.mode) !== selectedMode
      ) {
        return false
      }

      if (isBonus && selectedStage !== null && record.stage !== selectedStage) {
        return false
      }
      if (!isBonus && selectedTier !== "all") {
        const normalizedTier = normalizeTierValue(record.map_tier)
        if (normalizedTier !== Number(selectedTier)) {
          return false
        }
      }

      if (parsedMinPoints !== null && Number.isFinite(parsedMinPoints)) {
        if (record.points < parsedMinPoints) {
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
    minPoints,
    maxPoints,
    recordsQuery.data,
    selectedMode,
    selectedTier,
    selectedStage,
    isBonus,
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

  const filterEmptyMessage = isBonus
    ? "No bonus records found for this player with the current filters."
    : isProOnly
      ? "No stage 0 pro records found for this player with the current filters."
      : "No stage 0 records found for this player with the current filters."

  const hasActiveClientFilters =
    deferredMapSearch.trim().length > 0 ||
    deferredServerSearch.trim().length > 0 ||
    selectedMode !== "all" ||
    (!isBonus && selectedTier !== "all") ||
    (isBonus && selectedStage !== null) ||
    minPoints.trim().length > 0 ||
    maxPoints.trim().length > 0

  const emptyMessage = hasActiveClientFilters
    ? filterEmptyMessage
    : isBonus
      ? "No bonus records found for this player in the selected scope."
      : isProOnly
        ? "No stage 0 pro records found for this player in the selected scope."
        : "No stage 0 records found for this player in the selected scope."
  const recordType = isProOnly ? "PRO" : "NUB"
  const stageOptions = [
    ...new Set((recordsQuery.data ?? []).map((record) => record.stage)),
  ].sort((a, b) => a - b)
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
      <RowContextMenuItem
        disabled={pinnedRecordsMutating}
        onSelect={() => {
          if (isPinned) {
            onUnpinRecord(record.map_id, recordType)
            return
          }
          onPinRecord(record.map_id, recordType)
        }}
      >
        {isPinned ? <PinOff /> : <Pin />}
        {isPinned ? "Unpin this record" : "Pin this record"}
      </RowContextMenuItem>
    )
  }

  const renderAdminActions = (record: RecordPublic) => (
    <DeleteCourseRecordsButton
      bulkDeleteMutation={bulkDeleteMutation}
      record={record}
    />
  )

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
              ...(isBonus ? ["stage" as const] : ["tier" as const]),
              "tps",
              "time",
              "points",
              ...(!isBonus ? ["rating" as const] : []),
              "server",
              "datetime",
            ]}
            showReplayColumn
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
              tier: !isBonus ? (
                <TierSelector
                  value={selectedTier}
                  onValueChange={setSelectedTier}
                  allLabel="Tier"
                  triggerClassName="h-8 border-border/70 bg-background/80 text-xs"
                  ariaLabel="Filter by tier"
                />
              ) : undefined,
              stage: isBonus ? (
                <select
                  aria-label="Filter by stage"
                  value={selectedStage ?? "all"}
                  onChange={(event) =>
                    setSelectedStage(
                      event.target.value === "all"
                        ? null
                        : Number(event.target.value),
                    )
                  }
                  className="h-8 rounded-md border border-border/70 bg-background/80 px-2 text-xs"
                >
                  <option value="all">Stage</option>
                  {stageOptions.map((stage) => (
                    <option key={stage} value={stage}>
                      {stage}
                    </option>
                  ))}
                </select>
              ) : undefined,
              points: (
                <PointsRangeFilter
                  minPoints={minPoints}
                  maxPoints={maxPoints}
                  onMinPointsChange={setMinPoints}
                  onMaxPointsChange={setMaxPoints}
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
            onRowClick={setHistoryRecord}
            getRowContextMenu={getRowContextMenu}
            renderAdminActions={
              adminModeForRecords ? renderAdminActions : undefined
            }
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
      <RecordRunHistoryDialog
        identifier={steamid64}
        initialType={recordType}
        onOpenChange={(open) => {
          if (!open) {
            setHistoryRecord(null)
          }
        }}
        open={historyRecord !== null}
        record={historyRecord}
        scope={scope}
      />
    </div>
  )
}
