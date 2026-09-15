import { useQuery } from "@tanstack/react-query"
import { CalendarDaysIcon, ChevronDownIcon, Pin, PinOff } from "lucide-react"
import {
  type Dispatch,
  type SetStateAction,
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
import { ModeSelector } from "@/components/Common/ModeSelector"
import { TierSelector } from "@/components/Common/TierSelector"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import { normalizeRecordMode } from "@/components/Records/mode"
import { PbRecordsTable } from "@/components/Records/PbRecordsTable"
import {
  type PbRecordsColumn,
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
import { type DateTimePreset, getBrowserLocale } from "@/lib/date-time"
import { canModerateBansAndRecords } from "@/lib/user-roles"
import { cn } from "@/lib/utils"
import { RowContextMenuItem } from "../Common/RowContextMenu"
import {
  DeleteCourseRecordsButton,
  useRecordAdminActions,
} from "../Records/admin-actions"
import type { ProfileRecordsViewState } from "./ProfileRecordsPresetMenu"
import {
  getProfilePbRecordsQueryOptions,
  getProfilePinnedRecordKey,
} from "./profile-utils"

const PROFILE_RECORDS_PAGE_SIZE = 50
const SCORE_RANGE_MIN = 0
const SCORE_RANGE_MAX = 1000
const POINTS_RANGE_PRESETS = [
  { label: "0 ~ 799", min: 0, max: 799 },
  { label: "800 ~ 899", min: 800, max: 899 },
  { label: "900 ~ 1000", min: 900, max: 1000 },
] as const

function parseBound(value: string, fallback: number, max?: number) {
  const trimmedValue = value.trim()
  if (trimmedValue.length === 0) {
    return fallback
  }

  const parsedValue = Number(trimmedValue)
  if (!Number.isFinite(parsedValue)) {
    return fallback
  }

  const roundedValue = Math.max(0, Math.round(parsedValue))
  return max === undefined ? roundedValue : Math.min(max, roundedValue)
}

function getLocalDateKey(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value.slice(0, 10)
  }

  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${date.getFullYear()}-${month}-${day}`
}

type DateInputPart = "year" | "month" | "day"

interface DateInputPattern {
  order: DateInputPart[]
  parts: Intl.DateTimeFormatPart[]
  placeholder: string
  separators: string[]
}

function getDateInputPattern(preset: DateTimePreset): DateInputPattern {
  const parts: Intl.DateTimeFormatPart[] =
    preset === "iso"
      ? [
          { type: "year", value: "2006" },
          { type: "literal", value: "-" },
          { type: "month", value: "11" },
          { type: "literal", value: "-" },
          { type: "day", value: "22" },
        ]
      : preset === "us"
        ? new Intl.DateTimeFormat("en-US", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
          }).formatToParts(new Date(2006, 10, 22))
        : preset === "euro"
          ? new Intl.DateTimeFormat("en-GB", {
              year: "numeric",
              month: "2-digit",
              day: "2-digit",
            }).formatToParts(new Date(2006, 10, 22))
          : new Intl.DateTimeFormat(getBrowserLocale(), {
              year: "numeric",
              month: "2-digit",
              day: "2-digit",
            }).formatToParts(new Date(2006, 10, 22))
  const order = parts.flatMap((part) =>
    part.type === "year" || part.type === "month" || part.type === "day"
      ? [part.type as DateInputPart]
      : [],
  )
  const placeholder = parts
    .map((part) => {
      if (part.type === "year") {
        return "yyyy"
      }
      if (part.type === "month") {
        return "mm"
      }
      if (part.type === "day") {
        return "dd"
      }
      return part.value
    })
    .join("")
  const separators: string[] = []
  let encounteredDatePart = false
  let pendingSeparator = ""
  for (const part of parts) {
    if (part.type === "year" || part.type === "month" || part.type === "day") {
      if (encounteredDatePart) {
        separators.push(pendingSeparator)
      }
      encounteredDatePart = true
      pendingSeparator = ""
    } else if (encounteredDatePart) {
      pendingSeparator += part.value
    }
  }

  return { order, parts, placeholder, separators }
}

function formatPartialDateInputValue(value: string, pattern: DateInputPattern) {
  const digits = value.replace(/\D/g, "").slice(0, 8)
  let offset = 0
  const formattedParts: string[] = []

  for (const [index, part] of pattern.order.entries()) {
    const partLength = part === "year" ? 4 : 2
    const nextValue = digits.slice(offset, offset + partLength)
    if (!nextValue) {
      break
    }

    formattedParts.push(nextValue)
    offset += nextValue.length
    if (offset < digits.length) {
      formattedParts.push(pattern.separators[index] ?? "")
    }
  }

  return formattedParts.join("")
}

function formatDateInputValue(value: string, pattern: DateInputPattern) {
  const [year, month, day] = value.split("-")
  if (!year || !month || !day) {
    return ""
  }

  const values: Record<DateInputPart, string> = { year, month, day }
  return pattern.parts
    .map((part) =>
      part.type === "year" || part.type === "month" || part.type === "day"
        ? values[part.type]
        : part.value,
    )
    .join("")
}

function parseDateInputValue(value: string, pattern: DateInputPattern) {
  const numericParts = value.match(/\d+/g)
  if (!numericParts || numericParts.length !== 3) {
    return null
  }

  const values = Object.fromEntries(
    pattern.order.map((part, index) => [part, Number(numericParts[index])]),
  ) as Record<DateInputPart, number>
  const candidate = new Date(values.year, values.month - 1, values.day)
  if (
    values.year < 1000 ||
    candidate.getFullYear() !== values.year ||
    candidate.getMonth() !== values.month - 1 ||
    candidate.getDate() !== values.day
  ) {
    return null
  }

  return `${String(values.year).padStart(4, "0")}-${String(values.month).padStart(2, "0")}-${String(values.day).padStart(2, "0")}`
}

function PreferenceDateInput({
  id,
  label,
  value,
  min,
  max,
  onValueChange,
}: {
  id: string
  label: string
  value: string
  min?: string
  max?: string
  onValueChange: (value: string) => void
}) {
  const { preset } = useDateTimeFormat()
  const pattern = getDateInputPattern(preset)
  const [draftValue, setDraftValue] = useState(() =>
    formatDateInputValue(value, pattern),
  )
  const pickerRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    setDraftValue(formatDateInputValue(value, getDateInputPattern(preset)))
  }, [preset, value])

  const commitValue = () => {
    const trimmedValue = draftValue.trim()
    if (!trimmedValue) {
      onValueChange("")
      setDraftValue("")
      return
    }

    const parsedValue = parseDateInputValue(trimmedValue, pattern)
    if (parsedValue) {
      onValueChange(parsedValue)
      setDraftValue(formatDateInputValue(parsedValue, pattern))
    } else {
      setDraftValue(formatDateInputValue(value, pattern))
    }
  }

  return (
    <div className="relative">
      <Input
        id={id}
        type="text"
        inputMode="numeric"
        value={draftValue}
        placeholder={pattern.placeholder}
        onChange={(event) =>
          setDraftValue(
            formatPartialDateInputValue(event.target.value, pattern),
          )
        }
        onBlur={commitValue}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault()
            event.currentTarget.blur()
          }
        }}
        aria-label={`${label} date`}
        className="h-8 pr-8 pl-2 font-mono text-xs"
      />
      <input
        ref={pickerRef}
        type="date"
        value={value}
        min={min}
        max={max}
        onChange={(event) => onValueChange(event.target.value)}
        aria-label={`Choose ${label.toLocaleLowerCase()} date`}
        className="sr-only"
        tabIndex={-1}
      />
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={`Open ${label.toLocaleLowerCase()} date picker`}
        title={`Open ${label.toLocaleLowerCase()} date picker`}
        className="absolute top-0 right-0 h-8 w-8 text-muted-foreground"
        onClick={() => {
          const picker = pickerRef.current
          if (!picker) {
            return
          }
          if (typeof picker.showPicker === "function") {
            picker.showPicker()
          } else {
            picker.click()
          }
        }}
      >
        <CalendarDaysIcon />
      </Button>
    </div>
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

function NumericRangeFilter({
  label,
  idPrefix,
  minValue,
  maxValue,
  onMinValueChange,
  onMaxValueChange,
  maxBound,
  presets = [],
}: {
  label: string
  idPrefix: string
  minValue: string
  maxValue: string
  onMinValueChange: (value: string) => void
  onMaxValueChange: (value: string) => void
  maxBound?: number
  presets?: ReadonlyArray<{ label: string; min: number; max: number }>
}) {
  const effectiveMinValue = parseBound(minValue, SCORE_RANGE_MIN, maxBound)
  const parsedMaxValue =
    maxValue.trim().length === 0
      ? null
      : parseBound(maxValue, SCORE_RANGE_MIN, maxBound)
  const effectiveMaxValue = parsedMaxValue ?? maxBound
  const trimmedMinValue = minValue.trim()
  const trimmedMaxValue = maxValue.trim()
  const hasActiveRange =
    trimmedMinValue.length > 0 || trimmedMaxValue.length > 0
  const activeRangeLabel =
    effectiveMaxValue !== undefined
      ? `${effectiveMinValue} ~ ${effectiveMaxValue}`
      : trimmedMinValue.length > 0
        ? `${effectiveMinValue}+`
        : null
  const rangeLabel = hasActiveRange
    ? (activeRangeLabel ?? `0 ~ ${parsedMaxValue}`)
    : null
  const accessibleLabel =
    label === label.toUpperCase() ? label : label.toLowerCase()
  const commitRange = (
    nextMin = effectiveMinValue,
    nextMax = effectiveMaxValue,
  ) => {
    const normalizedMin = parseBound(String(nextMin), SCORE_RANGE_MIN, maxBound)
    const normalizedMax =
      nextMax === undefined
        ? undefined
        : Math.max(
            normalizedMin,
            parseBound(String(nextMax), normalizedMin, maxBound),
          )

    onMinValueChange(
      normalizedMin === SCORE_RANGE_MIN ? "" : String(normalizedMin),
    )
    onMaxValueChange(
      normalizedMax === undefined || normalizedMax === maxBound
        ? ""
        : String(normalizedMax),
    )
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
          aria-label={`Filter by ${accessibleLabel} range`}
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
            <span>{label}</span>
            {maxBound !== undefined ? (
              <span className="font-mono text-foreground">
                {effectiveMinValue} ~ {effectiveMaxValue}
              </span>
            ) : null}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label
              htmlFor={`profile-records-${idPrefix}-min`}
              className="space-y-1 text-[11px] text-muted-foreground"
            >
              <span>Min</span>
              <Input
                id={`profile-records-${idPrefix}-min`}
                type="number"
                inputMode="numeric"
                min={SCORE_RANGE_MIN}
                max={effectiveMaxValue}
                step={1}
                value={minValue}
                placeholder={String(SCORE_RANGE_MIN)}
                onChange={(event) => {
                  onMinValueChange(event.target.value)
                }}
                onBlur={() => commitRange()}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    event.currentTarget.blur()
                  }
                }}
                aria-label={`Minimum ${accessibleLabel}`}
                className="h-8 px-2 text-center font-mono text-xs [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
              />
            </label>
            <label
              htmlFor={`profile-records-${idPrefix}-max`}
              className="space-y-1 text-[11px] text-muted-foreground"
            >
              <span>Max</span>
              <Input
                id={`profile-records-${idPrefix}-max`}
                type="number"
                inputMode="numeric"
                min={effectiveMinValue}
                max={maxBound}
                step={1}
                value={maxValue}
                placeholder={
                  maxBound === undefined ? "No max" : String(maxBound)
                }
                onChange={(event) => {
                  onMaxValueChange(event.target.value)
                }}
                onBlur={() => commitRange()}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    event.currentTarget.blur()
                  }
                }}
                aria-label={`Maximum ${accessibleLabel}`}
                className="h-8 px-2 text-center font-mono text-xs [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
              />
            </label>
          </div>
          {maxBound !== undefined && effectiveMaxValue !== undefined ? (
            <div className="space-y-2">
              <div className="space-y-1">
                <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  <span>Min</span>
                  <span className="font-mono text-foreground">
                    {effectiveMinValue}
                  </span>
                </div>
                <input
                  type="range"
                  min={SCORE_RANGE_MIN}
                  max={effectiveMaxValue}
                  step={1}
                  value={effectiveMinValue}
                  onChange={(event) => {
                    commitRange(Number(event.target.value), effectiveMaxValue)
                  }}
                  className={sliderClassName}
                  aria-label={`Minimum ${accessibleLabel} slider`}
                />
              </div>
              <div className="space-y-1">
                <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  <span>Max</span>
                  <span className="font-mono text-foreground">
                    {effectiveMaxValue}
                  </span>
                </div>
                <input
                  type="range"
                  min={effectiveMinValue}
                  max={maxBound}
                  step={1}
                  value={effectiveMaxValue}
                  onChange={(event) => {
                    commitRange(effectiveMinValue, Number(event.target.value))
                  }}
                  className={sliderClassName}
                  aria-label={`Maximum ${accessibleLabel} slider`}
                />
              </div>
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-1.5">
            {presets.map((preset) => (
              <Button
                key={preset.label}
                type="button"
                variant="outline"
                size="sm"
                className="h-7 px-2 text-[10px] font-semibold tabular-nums"
                onClick={() => {
                  commitRange(preset.min, preset.max)
                }}
              >
                {preset.label}
              </Button>
            ))}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={cn(
                "h-7 px-2 text-[10px]",
                presets.length === 0 && "col-span-2",
              )}
              onClick={() => {
                onMinValueChange("")
                onMaxValueChange("")
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

function DateRangeFilter({
  fromDate,
  toDate,
  onFromDateChange,
  onToDateChange,
}: {
  fromDate: string
  toDate: string
  onFromDateChange: (value: string) => void
  onToDateChange: (value: string) => void
}) {
  const { preset } = useDateTimeFormat()
  const pattern = getDateInputPattern(preset)
  const formattedFromDate = formatDateInputValue(fromDate, pattern)
  const formattedToDate = formatDateInputValue(toDate, pattern)
  const hasActiveRange = fromDate.length > 0 || toDate.length > 0
  const rangeLabel =
    fromDate.length > 0 && toDate.length > 0
      ? `${formattedFromDate} ~ ${formattedToDate}`
      : fromDate.length > 0
        ? `${formattedFromDate}+`
        : `to ${formattedToDate}`
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Filter by date range"
          className={cn(
            "flex h-8 min-w-11 items-center justify-center rounded-md border border-border/70 bg-background/80 px-1.5 text-[11px] font-medium shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
            hasActiveRange ? "w-40" : "w-11",
            hasActiveRange && "border-primary/40 text-foreground",
          )}
        >
          <span className="flex min-w-0 items-center justify-center gap-1">
            {hasActiveRange ? (
              <span className="truncate text-[10px] font-semibold tabular-nums">
                {rangeLabel}
              </span>
            ) : null}
            <ChevronDownIcon className="size-3.5 shrink-0 opacity-50" />
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-72 space-y-3 p-3"
        onCloseAutoFocus={(event) => {
          event.preventDefault()
        }}
        onKeyDown={(event) => {
          event.stopPropagation()
        }}
      >
        <div className="space-y-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Date
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label
              htmlFor="profile-records-date-from"
              className="space-y-1 text-[11px] text-muted-foreground"
            >
              <span>From</span>
              <PreferenceDateInput
                id="profile-records-date-from"
                max={toDate || undefined}
                label="From"
                value={fromDate}
                onValueChange={(value) => {
                  onFromDateChange(value)
                  if (value && toDate && value > toDate) {
                    onToDateChange(value)
                  }
                }}
              />
            </label>
            <label
              htmlFor="profile-records-date-to"
              className="space-y-1 text-[11px] text-muted-foreground"
            >
              <span>To</span>
              <PreferenceDateInput
                id="profile-records-date-to"
                min={fromDate || undefined}
                label="To"
                value={toDate}
                onValueChange={(value) => {
                  onToDateChange(value)
                  if (value && fromDate && value < fromDate) {
                    onFromDateChange(value)
                  }
                }}
              />
            </label>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-full px-2 text-[10px]"
            onClick={() => {
              onFromDateChange("")
              onToDateChange("")
            }}
          >
            Reset
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function ProfileRecordsTab({
  steamid64,
  isProOnly,
  isBonus,
  viewState,
  onViewStateChange,
  canManagePinnedRecords,
  pinnedRecordKeys,
  pinnedRecordsMutating,
  onPinRecord,
  onUnpinRecord,
}: {
  steamid64: string
  isProOnly: boolean
  isBonus: boolean
  viewState: ProfileRecordsViewState
  onViewStateChange: Dispatch<SetStateAction<ProfileRecordsViewState>>
  canManagePinnedRecords: boolean
  pinnedRecordKeys: Set<string>
  pinnedRecordsMutating: boolean
  onPinRecord: (mapId: number, stage: number, type: "NUB" | "PRO") => void
  onUnpinRecord: (mapId: number, stage: number, type: "NUB" | "PRO") => void
}) {
  const { enabled: adminModeEnabled } = useAdminMode()
  const { user } = useAuth()
  const { scope } = useScope()
  const { bulkDeleteMutation } = useRecordAdminActions()
  const {
    mapSearch,
    selectedMode,
    selectedTier,
    selectedStage,
    minTeleports,
    maxTeleports,
    minPoints,
    maxPoints,
    minRating,
    maxRating,
    serverSearch,
    fromDate,
    toDate,
    sort,
  } = viewState
  const updateViewState = <Key extends keyof ProfileRecordsViewState>(
    key: Key,
    value: ProfileRecordsViewState[Key],
  ) => {
    onViewStateChange((current) => ({ ...current, [key]: value }))
  }
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
    const parsedMinTeleports =
      minTeleports.trim() === "" ? null : Number(minTeleports)
    const parsedMaxTeleports =
      maxTeleports.trim() === "" ? null : Number(maxTeleports)
    const parsedMinPoints = minPoints.trim() === "" ? null : Number(minPoints)
    const parsedMaxPoints = maxPoints.trim() === "" ? null : Number(maxPoints)
    const parsedMinRating = minRating.trim() === "" ? null : Number(minRating)
    const parsedMaxRating = maxRating.trim() === "" ? null : Number(maxRating)

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

      if (
        parsedMinTeleports !== null &&
        Number.isFinite(parsedMinTeleports) &&
        record.teleports < parsedMinTeleports
      ) {
        return false
      }

      if (
        parsedMaxTeleports !== null &&
        Number.isFinite(parsedMaxTeleports) &&
        record.teleports > parsedMaxTeleports
      ) {
        return false
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

      const ratingContribution = record.raw_rating_contribution ?? 0
      if (
        !isBonus &&
        parsedMinRating !== null &&
        Number.isFinite(parsedMinRating) &&
        ratingContribution < parsedMinRating
      ) {
        return false
      }

      if (
        !isBonus &&
        parsedMaxRating !== null &&
        Number.isFinite(parsedMaxRating) &&
        ratingContribution > parsedMaxRating
      ) {
        return false
      }

      const recordDate = getLocalDateKey(record.created_on)
      if (fromDate.length > 0 && recordDate < fromDate) {
        return false
      }

      if (toDate.length > 0 && recordDate > toDate) {
        return false
      }

      return true
    })

    return sortPbRecords(filteredRecords, sort)
  }, [
    deferredMapSearch,
    deferredServerSearch,
    minTeleports,
    maxTeleports,
    minPoints,
    maxPoints,
    minRating,
    maxRating,
    fromDate,
    toDate,
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
    updateViewState(
      "sort",
      sort.column === column
        ? {
            column,
            direction: sort.direction === "desc" ? "asc" : "desc",
          }
        : {
            column,
            direction: "desc",
          },
    )
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
    minTeleports.trim().length > 0 ||
    maxTeleports.trim().length > 0 ||
    minPoints.trim().length > 0 ||
    maxPoints.trim().length > 0 ||
    (!isBonus &&
      (minRating.trim().length > 0 || maxRating.trim().length > 0)) ||
    fromDate.length > 0 ||
    toDate.length > 0

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
        stage: record.stage,
        type: recordType,
      }),
    )

    return (
      <RowContextMenuItem
        disabled={pinnedRecordsMutating}
        onSelect={() => {
          if (isPinned) {
            onUnpinRecord(record.map_id, record.stage, recordType)
            return
          }
          onPinRecord(record.map_id, record.stage, recordType)
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
                  onChange={(event) =>
                    updateViewState("mapSearch", event.target.value)
                  }
                  placeholder="Search map"
                  className="h-8 w-56 border-border/70 bg-background/80 text-xs font-normal"
                />
              ),
              mode: (
                <ModeSelector
                  value={selectedMode}
                  onValueChange={(value) =>
                    updateViewState("selectedMode", value)
                  }
                  allLabel="Modes"
                  triggerClassName="data-[size=default]:h-8 border-border/70 bg-background/80 text-xs"
                  ariaLabel="Filter by mode"
                />
              ),
              tier: !isBonus ? (
                <TierSelector
                  value={selectedTier}
                  onValueChange={(value) =>
                    updateViewState("selectedTier", value)
                  }
                  allLabel="Tier"
                  triggerClassName="data-[size=default]:h-8 border-border/70 bg-background/80 text-xs"
                  ariaLabel="Filter by tier"
                />
              ) : undefined,
              stage: isBonus ? (
                <select
                  aria-label="Filter by stage"
                  value={selectedStage ?? "all"}
                  onChange={(event) =>
                    updateViewState(
                      "selectedStage",
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
              tps: (
                <NumericRangeFilter
                  label="TP"
                  idPrefix="teleports"
                  minValue={minTeleports}
                  maxValue={maxTeleports}
                  onMinValueChange={(value) =>
                    updateViewState("minTeleports", value)
                  }
                  onMaxValueChange={(value) =>
                    updateViewState("maxTeleports", value)
                  }
                />
              ),
              points: (
                <NumericRangeFilter
                  label="Points"
                  idPrefix="points"
                  minValue={minPoints}
                  maxValue={maxPoints}
                  onMinValueChange={(value) =>
                    updateViewState("minPoints", value)
                  }
                  onMaxValueChange={(value) =>
                    updateViewState("maxPoints", value)
                  }
                  maxBound={SCORE_RANGE_MAX}
                  presets={POINTS_RANGE_PRESETS}
                />
              ),
              rating: !isBonus ? (
                <NumericRangeFilter
                  label="Rating"
                  idPrefix="rating"
                  minValue={minRating}
                  maxValue={maxRating}
                  onMinValueChange={(value) =>
                    updateViewState("minRating", value)
                  }
                  onMaxValueChange={(value) =>
                    updateViewState("maxRating", value)
                  }
                  maxBound={SCORE_RANGE_MAX}
                />
              ) : undefined,
              server: (
                <Input
                  aria-label="Search server"
                  value={serverSearch}
                  onChange={(event) =>
                    updateViewState("serverSearch", event.target.value)
                  }
                  placeholder="Search server"
                  className="h-8 border-border/70 bg-background/80 text-xs font-normal"
                />
              ),
              datetime: (
                <DateRangeFilter
                  fromDate={fromDate}
                  toDate={toDate}
                  onFromDateChange={(value) =>
                    updateViewState("fromDate", value)
                  }
                  onToDateChange={(value) => updateViewState("toDate", value)}
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
