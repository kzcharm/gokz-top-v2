import { useQuery } from "@tanstack/react-query"
import { X } from "lucide-react"
import {
  useCallback,
  useEffect,
  useEffectEvent,
  useMemo,
  useState,
} from "react"

import { type MapPublic, MapsService } from "@/client"
import {
  useAdminMode,
  useAdminModeSurface,
} from "@/components/admin-mode-provider"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { type AppScope, useScope } from "@/components/scope-provider"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import useAuth from "@/hooks/useAuth"
import { canModerateBansAndRecords } from "@/lib/user-roles"
import { cn } from "@/lib/utils"

import {
  DeleteCourseRecordsButton,
  useRecordAdminActions,
} from "./admin-actions"
import { PointsBadge } from "./PointsBadge"
import { RecentRecordsTable } from "./RecentRecordsTable"
import { StageBadge } from "./StageBadge"
import { TeleportsBadge } from "./TeleportsBadge"
import {
  buildRecentRecordsWebSocketUrl,
  compareRecentRecords,
  fetchRecentRecords,
  RECENT_RECORDS_LIVE_LIMIT,
  type RecentRecord,
  type RecentRecordRealtimeEvent,
  type RecentRecordsFilters,
  upsertRecentRecord,
} from "./utils"

type RecordTypeFilter = "all" | "NUB" | "PRO"
type StageFilter = "all" | "main" | "bonus"
type PointsFilter = "all" | "pb" | "800-plus" | "900-plus" | "wr"

const STAGE_FILTER_OPTIONS: Array<{ label: string; value: StageFilter }> = [
  { label: "Main", value: "main" },
  { label: "Bonus", value: "bonus" },
]

const SCOPE_MODES: Record<AppScope, string[]> = {
  OVR: ["KZT", "SKZ", "VNL", "NKZ"],
  KZT: ["KZT", "NKZ"],
  SKZ: ["SKZ"],
  VNL: ["VNL"],
}

const RECORD_TYPE_FILTER_OPTIONS: Array<{
  label: string
  teleports: number
  value: RecordTypeFilter
}> = [
  { label: "NUB", teleports: 1, value: "NUB" },
  { label: "PRO", teleports: 0, value: "PRO" },
]

const POINTS_FILTER_OPTIONS: Array<{
  label: string
  points: number
  value: PointsFilter
}> = [
  { label: "PB", points: 1, value: "pb" },
  { label: "800+", points: 800, value: "800-plus" },
  { label: "900+", points: 900, value: "900-plus" },
  { label: "WR", points: 1000, value: "wr" },
]

function StageFilterContent({ value }: { value: StageFilter }) {
  if (value === "all") {
    return <span>Stage</span>
  }

  const option = STAGE_FILTER_OPTIONS.find((item) => item.value === value)
  const stage = value === "main" ? 0 : 1

  return (
    <StageBadge
      stage={stage}
      label={option?.label}
      className="min-w-16 justify-center px-2 py-0.5 text-[11px]"
    />
  )
}

function RecordTypeFilterContent({ value }: { value: RecordTypeFilter }) {
  if (value === "all") {
    return <span>NUB / PRO</span>
  }

  const option = RECORD_TYPE_FILTER_OPTIONS.find((item) => item.value === value)

  return option ? (
    <TeleportsBadge
      teleports={option.teleports}
      label={option.label}
      className="text-[11px]"
    />
  ) : null
}

function PointsFilterContent({ value }: { value: PointsFilter }) {
  if (value === "all") {
    return <span>Points</span>
  }

  const option = POINTS_FILTER_OPTIONS.find((item) => item.value === value)

  return option ? (
    <PointsBadge
      points={option.points}
      label={option.label}
      className="text-[11px]"
    />
  ) : null
}

function getPointsFilterBounds(pointsFilter: PointsFilter) {
  switch (pointsFilter) {
    case "pb":
      return { minPoints: 1, maxPoints: null }
    case "800-plus":
      return { minPoints: 800, maxPoints: null }
    case "900-plus":
      return { minPoints: 900, maxPoints: null }
    case "wr":
      return { minPoints: 1000, maxPoints: 1000 }
    default:
      return { minPoints: null, maxPoints: null }
  }
}

function MapPicker({
  inputValue,
  maps,
  mapsLoading,
  onInputChange,
  onSelectMap,
  onClear,
  selectedMap,
}: {
  inputValue: string
  maps: MapPublic[]
  mapsLoading: boolean
  onInputChange: (value: string) => void
  onSelectMap: (map: MapPublic) => void
  onClear: () => void
  selectedMap: Pick<MapPublic, "id" | "name"> | null
}) {
  const [focused, setFocused] = useState(false)
  const normalizedInput = inputValue.trim().toLocaleLowerCase()
  const matchingMaps = useMemo(() => {
    if (normalizedInput.length === 0) {
      return []
    }

    return maps
      .filter((map) => map.name.toLocaleLowerCase().includes(normalizedInput))
      .slice(0, 8)
  }, [maps, normalizedInput])
  const showOptions =
    focused && normalizedInput.length > 0 && selectedMap === null

  return (
    <div className="relative w-full sm:w-64">
      <Input
        aria-label="Choose map"
        role="combobox"
        aria-expanded={showOptions}
        aria-controls="recent-record-map-picker-options"
        value={inputValue}
        onChange={(event) => {
          onInputChange(event.target.value)
        }}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          window.setTimeout(() => setFocused(false), 100)
        }}
        placeholder="Choose map"
        className="!h-8 border-border/70 bg-background/80 pr-8 text-xs"
      />
      {selectedMap ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Clear selected map"
          className="absolute top-0.5 right-0.5 size-7"
          onClick={onClear}
        >
          <X className="size-3.5" />
        </Button>
      ) : null}
      {showOptions ? (
        <div
          id="recent-record-map-picker-options"
          role="listbox"
          className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md"
        >
          {mapsLoading ? (
            <div className="px-2 py-2 text-xs text-muted-foreground">
              Loading maps...
            </div>
          ) : matchingMaps.length > 0 ? (
            matchingMaps.map((map) => (
              <button
                key={map.id}
                type="button"
                role="option"
                aria-selected={false}
                className="flex w-full items-center rounded-sm px-2 py-1.5 text-left text-xs outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
                onMouseDown={(event) => {
                  event.preventDefault()
                  onSelectMap(map)
                  setFocused(false)
                }}
              >
                {map.name}
              </button>
            ))
          ) : (
            <div className="px-2 py-2 text-xs text-muted-foreground">
              No maps found.
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}

export function RecentRecordsPanel() {
  const { enabled: adminModeEnabled } = useAdminMode()
  const { user } = useAuth()
  const { scope } = useScope()
  const { bulkDeleteMutation } = useRecordAdminActions()
  const [records, setRecords] = useState<RecentRecord[]>([])
  const [mapInput, setMapInput] = useState("")
  const [selectedMap, setSelectedMap] = useState<Pick<
    MapPublic,
    "id" | "name"
  > | null>(null)
  const [selectedStage, setSelectedStage] = useState<StageFilter>("all")
  const [selectedTier, setSelectedTier] = useState<TierSelectorValue>("all")
  const [selectedType, setSelectedType] = useState<RecordTypeFilter>("all")
  const [selectedPoints, setSelectedPoints] = useState<PointsFilter>("all")
  const canUseRecordAdminActions = canModerateBansAndRecords(user)
  useAdminModeSurface(canUseRecordAdminActions)
  const canAdministerRecords = adminModeEnabled && canUseRecordAdminActions
  const mapsQuery = useQuery({
    queryKey: ["maps", "picker", "validated"],
    queryFn: () =>
      MapsService.readMaps({
        offset: 0,
        limit: 100000,
        isValidated: true,
      }),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  const filters = useMemo<RecentRecordsFilters>(() => {
    const pointsBounds = getPointsFilterBounds(selectedPoints)
    return {
      scope,
      mapId: selectedMap?.id ?? null,
      stage: selectedStage === "main" ? 0 : null,
      isBonus: selectedStage === "bonus" ? true : null,
      tier: selectedTier === "all" ? null : Number(selectedTier),
      type: selectedType === "all" ? null : selectedType,
      minPoints: pointsBounds.minPoints,
      maxPoints: pointsBounds.maxPoints,
    }
  }, [
    selectedMap,
    selectedPoints,
    selectedStage,
    selectedTier,
    selectedType,
    scope,
  ])

  const hasActiveFilters =
    filters.mapId !== null ||
    filters.stage !== null ||
    filters.isBonus !== null ||
    filters.tier !== null ||
    filters.type !== null ||
    filters.minPoints !== null ||
    filters.maxPoints !== null

  const recordsQuery = useQuery({
    queryKey: ["recent-records", "dashboard", filters],
    queryFn: () => fetchRecentRecords(RECENT_RECORDS_LIVE_LIMIT, filters),
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  useEffect(() => {
    if (!recordsQuery.data) {
      return
    }

    setRecords(
      [...recordsQuery.data.data]
        .sort(compareRecentRecords)
        .slice(0, RECENT_RECORDS_LIVE_LIMIT),
    )
  }, [recordsQuery.data])

  const recordMatchesFilters = useCallback(
    (record: RecentRecord) => {
      if (!SCOPE_MODES[scope].includes(record.mode.name)) {
        return false
      }
      if (filters.mapId !== null && record.map.id !== filters.mapId) {
        return false
      }
      if (filters.stage !== null && record.stage !== filters.stage) {
        return false
      }
      if (filters.isBonus === true && record.stage <= 0) {
        return false
      }
      if (filters.tier !== null && record.map.tier !== filters.tier) {
        return false
      }
      if (filters.type === "PRO" && record.teleports !== 0) {
        return false
      }
      if (filters.type === "NUB" && record.teleports <= 0) {
        return false
      }
      if (
        filters.minPoints !== null &&
        filters.minPoints !== undefined &&
        record.points < filters.minPoints
      ) {
        return false
      }
      if (
        filters.maxPoints !== null &&
        filters.maxPoints !== undefined &&
        record.points > filters.maxPoints
      ) {
        return false
      }
      return true
    },
    [filters, scope],
  )

  const handleRealtimeEvent = useEffectEvent(
    (event: RecentRecordRealtimeEvent) => {
      setRecords((currentRecords) => {
        if (event.type === "record.snapshot") {
          return [...event.records]
            .filter(recordMatchesFilters)
            .sort(compareRecentRecords)
            .slice(0, RECENT_RECORDS_LIVE_LIMIT)
        }

        if (!recordMatchesFilters(event.record)) {
          return currentRecords.filter(
            (currentRecord) => currentRecord.uuid !== event.record.uuid,
          )
        }

        return upsertRecentRecord(
          currentRecords,
          event.record,
          RECENT_RECORDS_LIVE_LIMIT,
        )
      })
    },
  )

  const visibleRecords = useMemo(
    () => records.filter(recordMatchesFilters),
    [recordMatchesFilters, records],
  )

  useEffect(() => {
    let websocket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0
    let shouldReconnect = true

    const connect = () => {
      websocket = new WebSocket(buildRecentRecordsWebSocketUrl(scope))

      websocket.onopen = () => {
        attempt = 0
      }

      websocket.onmessage = (message) => {
        try {
          handleRealtimeEvent(
            JSON.parse(message.data) as RecentRecordRealtimeEvent,
          )
        } catch {
          websocket?.close()
        }
      }

      websocket.onclose = () => {
        if (!shouldReconnect) {
          return
        }

        attempt += 1
        const delay = Math.min(1000 * 2 ** attempt, 15000)
        reconnectTimer = setTimeout(connect, delay)
      }

      websocket.onerror = () => {
        websocket?.close()
      }
    }

    connect()

    return () => {
      shouldReconnect = false
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      websocket?.close()
    }
  }, [scope])

  return (
    <div className="flex flex-col gap-4">
      {recordsQuery.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load recent records. Reload the page and try again.
          </AlertDescription>
        </Alert>
      ) : null}

      <Card className="w-full max-w-full min-w-0 gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="min-w-0 p-4 sm:p-6">
          <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <MapPicker
              inputValue={selectedMap ? selectedMap.name : mapInput}
              maps={mapsQuery.data ?? []}
              mapsLoading={mapsQuery.isLoading}
              selectedMap={selectedMap}
              onInputChange={(value) => {
                setMapInput(value)
                setSelectedMap(null)
              }}
              onSelectMap={(map) => {
                setSelectedMap({ id: map.id, name: map.name })
                setMapInput(map.name)
              }}
              onClear={() => {
                setSelectedMap(null)
                setMapInput("")
              }}
            />
            <Select
              value={selectedStage}
              onValueChange={(value) => setSelectedStage(value as StageFilter)}
            >
              <SelectTrigger
                aria-label="Filter recent records by stage"
                className="h-8 w-full border-border/70 bg-background/80 text-xs sm:w-28"
              >
                <StageFilterContent value={selectedStage} />
              </SelectTrigger>
              <SelectContent align="start">
                <SelectItem value="all">Stage</SelectItem>
                {STAGE_FILTER_OPTIONS.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    textValue={option.label}
                  >
                    <StageFilterContent value={option.value} />
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <TierSelector
              value={selectedTier}
              onValueChange={setSelectedTier}
              allLabel="Tier"
              triggerClassName="h-8 w-full min-w-16 border-border/70 bg-background/80 text-xs sm:w-auto"
              ariaLabel="Filter recent records by tier"
              showAllLabelInTrigger
            />
            <Select
              value={selectedType}
              onValueChange={(value) =>
                setSelectedType(value as RecordTypeFilter)
              }
            >
              <SelectTrigger
                aria-label="Filter recent records by NUB or PRO"
                className="h-8 w-full border-border/70 bg-background/80 text-xs sm:w-28"
              >
                <RecordTypeFilterContent value={selectedType} />
              </SelectTrigger>
              <SelectContent align="start">
                <SelectItem value="all">NUB / PRO</SelectItem>
                {RECORD_TYPE_FILTER_OPTIONS.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    textValue={option.label}
                  >
                    <RecordTypeFilterContent value={option.value} />
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={selectedPoints}
              onValueChange={(value) =>
                setSelectedPoints(value as PointsFilter)
              }
            >
              <SelectTrigger
                aria-label="Filter recent records by points"
                className={cn(
                  "h-8 w-full border-border/70 bg-background/80 text-xs",
                  selectedPoints === "all" ? "sm:w-24" : "sm:w-28",
                )}
              >
                <PointsFilterContent value={selectedPoints} />
              </SelectTrigger>
              <SelectContent align="start">
                <SelectItem value="all" textValue="Points">
                  <PointsFilterContent value="all" />
                </SelectItem>
                {POINTS_FILTER_OPTIONS.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    textValue={option.label}
                  >
                    <PointsFilterContent value={option.value} />
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <RecentRecordsTable
        records={visibleRecords}
        emptyMessage={
          hasActiveFilters
            ? "No recent records match the current filters."
            : undefined
        }
        renderAdminActions={
          canAdministerRecords
            ? (record) => (
                <DeleteCourseRecordsButton
                  bulkDeleteMutation={bulkDeleteMutation}
                  record={{
                    player: {
                      display_name: record.player.alias ?? record.player.name,
                      steamid64: record.player.steamid64,
                    },
                    map_id: record.map.id,
                    map_name: record.map.name,
                    stage: record.stage,
                  }}
                />
              )
            : undefined
        }
      />
    </div>
  )
}
