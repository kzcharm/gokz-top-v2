import { useQuery } from "@tanstack/react-query"
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Copy,
  Download,
  Filter,
  Globe,
  Search,
  SearchX,
} from "lucide-react"
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
} from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import {
  LeaderboardsService,
  type MapLeaderboardEntryPublic,
  type MapPublic,
  MapsService,
  type MapWrPublic,
} from "@/client"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { useKeyboardPagination } from "@/components/Common/WASDNavigation"
import { MapCard } from "@/components/Maps/MapCard"
import {
  getMapSkillPercentage,
  getMapTierForScope,
  MAP_SORTABLE_SKILLS,
  type MapSkillKey,
} from "@/components/Maps/map-utils"
import { PendingMaps } from "@/components/Maps/PendingMaps"
import { normalizeTierValue } from "@/components/Servers/tier"
import { type AppScope, useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import { compareLocaleText, formatNumber } from "@/i18n/locale"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 24
const POSIX_DOWNLOAD_COMMAND =
  "curl -fsSL https://gokz.top/install/maps.sh | sh"
const POWERSHELL_DOWNLOAD_COMMAND =
  'powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://gokz.top/install/maps.ps1 | iex"'

const MAP_SORT_OPTIONS = [
  { labelKey: "maps.sortOptions.name", value: "name" },
  { labelKey: "maps.sortOptions.tier", value: "tier" },
  { labelKey: "maps.sortOptions.created", value: "created" },
  { labelKey: "maps.sortOptions.updated", value: "updated" },
  { labelKey: "maps.sortOptions.wr", value: "wr" },
  { labelKey: "maps.sortOptions.review", value: "review" },
  { labelKey: "maps.sortOptions.metrics", value: "metrics" },
  { labelKey: "maps.sortOptions.bonus", value: "bonus" },
  { labelKey: "maps.sortOptions.skill", value: "skill" },
] as const

const METRIC_SORT_OPTIONS = [
  { labelKey: "maps.sortOptions.playtime", value: "playtime" },
  { labelKey: "maps.sortOptions.avgPlaytime", value: "avgPlaytime" },
  { labelKey: "maps.sortOptions.nub", value: "nub" },
  { labelKey: "maps.sortOptions.pro", value: "pro" },
  { labelKey: "maps.sortOptions.proRatio", value: "proRatio" },
  { labelKey: "maps.sortOptions.finishes", value: "finishes" },
  { labelKey: "maps.sortOptions.firstMed", value: "firstMed" },
] as const

const REVIEW_SORT_OPTIONS = [
  { labelKey: "maps.sortOptions.overall", value: "overall" },
  { labelKey: "maps.sortOptions.gameplay", value: "gameplay" },
  { labelKey: "maps.sortOptions.visuals", value: "visuals" },
  { labelKey: "maps.sortOptions.reviewCount", value: "reviewCount" },
  { labelKey: "maps.sortOptions.commentsCount", value: "commentsCount" },
] as const

type MapsSortOption = (typeof MAP_SORT_OPTIONS)[number]["value"]
type MetricSortField = (typeof METRIC_SORT_OPTIONS)[number]["value"]
type ReviewSortField = (typeof REVIEW_SORT_OPTIONS)[number]["value"]
type MapsSortField =
  | Exclude<MapsSortOption, "review">
  | ReviewSortField
  | MetricSortField
type MapsSortDirection = "asc" | "desc"
type SortableSkillKey = Exclude<MapSkillKey, "unknown">
type MapValidationStatus = "validated" | "invalid"

type MapFilterValues = {
  wrMin: string
  wrMax: string
  createdMin: string
  createdMax: string
  updatedMin: string
  updatedMax: string
  ratingMin: string
  ratingMax: string
  reviewsMin: string
  reviewsMax: string
  commentsMin: string
  commentsMax: string
}

const EMPTY_MAP_FILTERS: MapFilterValues = {
  wrMin: "",
  wrMax: "",
  createdMin: "",
  createdMax: "",
  updatedMin: "",
  updatedMax: "",
  ratingMin: "",
  ratingMax: "",
  reviewsMin: "",
  reviewsMax: "",
  commentsMin: "",
  commentsMax: "",
}

const MAPS_CATALOG_STORAGE_KEY = "gokz.maps.catalog.state"

type PersistedMapsCatalogState = {
  searchInput: string
  sortField: MapsSortField
  sortDirection: MapsSortDirection
  selectedSkill: SortableSkillKey
  selectedReviewSort: ReviewSortField
  selectedTier: TierSelectorValue
  minimumTier: TierSelectorValue
  maximumTier: TierSelectorValue
  withBonusOnly: boolean
  validationStatus: MapValidationStatus
  mapFilters: MapFilterValues
  page: number
}

function readPersistedMapsCatalogState(): Partial<PersistedMapsCatalogState> {
  if (typeof window === "undefined") {
    return {}
  }

  try {
    const stored = window.sessionStorage.getItem(MAPS_CATALOG_STORAGE_KEY)
    if (!stored) {
      return {}
    }
    const parsed: unknown = JSON.parse(stored)
    return parsed && typeof parsed === "object"
      ? (parsed as Partial<PersistedMapsCatalogState>)
      : {}
  } catch {
    return {}
  }
}

function isMapsSortField(value: unknown): value is MapsSortField {
  return (
    typeof value === "string" &&
    (MAP_SORT_OPTIONS.some((option) => option.value === value) ||
      REVIEW_SORT_OPTIONS.some((option) => option.value === value) ||
      METRIC_SORT_OPTIONS.some((option) => option.value === value))
  )
}

function isTierSelectorValue(value: unknown): value is TierSelectorValue {
  return (
    value === "all" ||
    value === "none" ||
    (typeof value === "string" && /^\d+$/.test(value))
  )
}

function isSortableSkillKey(value: unknown): value is SortableSkillKey {
  return MAP_SORTABLE_SKILLS.some((skill) => skill.key === value)
}

function isMapValidationStatus(value: unknown): value is MapValidationStatus {
  return value === "validated" || value === "invalid"
}

function parseWrTime(value: string) {
  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }

  if (/^\d+(?:\.\d+)?$/.test(trimmed)) {
    const seconds = Number(trimmed)
    return Number.isFinite(seconds) && seconds >= 0 ? seconds : null
  }

  const match = /^(\d+):(\d{1,2})(?:\.(\d+))?$/.exec(trimmed)
  if (!match) {
    return null
  }

  const minutes = Number(match[1])
  const seconds = Number(`${match[2]}${match[3] ? `.${match[3]}` : ""}`)
  return seconds < 60 ? minutes * 60 + seconds : null
}

function parseNumber(value: string) {
  if (!value.trim()) {
    return null
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

function parseDateBound(value: string, endOfDay = false) {
  if (!value) {
    return null
  }
  const parsed = Date.parse(
    `${value}T${endOfDay ? "23:59:59.999" : "00:00:00.000"}Z`,
  )
  return Number.isFinite(parsed) ? parsed : null
}

function hasValue(value: string) {
  return value.trim() !== ""
}

function isRangeReversed(
  min: string,
  max: string,
  parser: (value: string) => number | null,
) {
  const minValue = parser(min)
  const maxValue = parser(max)
  return (
    hasValue(min) &&
    hasValue(max) &&
    minValue !== null &&
    maxValue !== null &&
    minValue > maxValue
  )
}

function isInvalidValue(
  value: string,
  parser: (value: string) => number | null,
) {
  return hasValue(value) && parser(value) === null
}

function RangeInputs({
  id,
  label,
  min,
  max,
  onMinChange,
  onMaxChange,
  minPlaceholder,
  maxPlaceholder,
  type = "number",
  inputMode = "decimal",
}: {
  id: string
  label: string
  min: string
  max: string
  onMinChange: (value: string) => void
  onMaxChange: (value: string) => void
  minPlaceholder: string
  maxPlaceholder: string
  type?: "date" | "number" | "text"
  inputMode?: "decimal" | "numeric" | "text"
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-2">
      <Label htmlFor={`${id}-min`}>{label}</Label>
      <div className="grid grid-cols-2 gap-2">
        <Input
          id={`${id}-min`}
          type={type}
          inputMode={inputMode}
          value={min}
          onChange={(event) => onMinChange(event.target.value)}
          placeholder={minPlaceholder}
          aria-label={`${label} ${t("maps.filterMin")}`}
          min={type === "number" ? 0 : undefined}
        />
        <Input
          id={`${id}-max`}
          type={type}
          inputMode={inputMode}
          value={max}
          onChange={(event) => onMaxChange(event.target.value)}
          placeholder={maxPlaceholder}
          aria-label={`${label} ${t("maps.filterMax")}`}
          min={type === "number" ? 0 : undefined}
        />
      </div>
    </div>
  )
}

function isReviewSortField(value: unknown): value is ReviewSortField {
  return REVIEW_SORT_OPTIONS.some((option) => option.value === value)
}

function SortableMapOption({
  active,
  direction,
  label,
  tooltip,
  onClick,
}: {
  active: boolean
  direction?: MapsSortDirection
  label: string
  tooltip?: string
  onClick: () => void
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      className={cn(
        "-ml-3 h-8 px-3 text-left text-sm",
        active ? "text-foreground" : "text-muted-foreground",
      )}
      aria-pressed={active}
      onClick={onClick}
    >
      <span title={tooltip}>{label}</span>
      {active ? (
        direction === "asc" ? (
          <ArrowUp className="ml-2 size-4" />
        ) : (
          <ArrowDown className="ml-2 size-4" />
        )
      ) : null}
    </Button>
  )
}

function compareNullableNumbers(
  left: number | null | undefined,
  right: number | null | undefined,
  direction: MapsSortDirection,
) {
  const leftIsNull = left === null || left === undefined
  const rightIsNull = right === null || right === undefined

  if (leftIsNull && rightIsNull) {
    return 0
  }
  if (leftIsNull) {
    return 1
  }
  if (rightIsNull) {
    return -1
  }

  const comparison = left - right
  return direction === "asc" ? comparison : -comparison
}

function sortMaps(
  maps: MapPublic[],
  sortField: MapsSortField,
  sortDirection: MapsSortDirection,
  scope: AppScope,
  selectedSkill: SortableSkillKey,
  wrTimeByMapId: ReadonlyMap<number, number>,
  leaderboardByMapId: ReadonlyMap<number, MapLeaderboardEntryPublic>,
) {
  return [...maps].sort((left, right) => {
    const leftTier = getMapTierForScope(left, scope)
    const rightTier = getMapTierForScope(right, scope)
    const leftReviewSummary = left.review_summary
    const rightReviewSummary = right.review_summary

    let comparison = 0

    switch (sortField) {
      case "tier":
        comparison = compareNullableNumbers(leftTier, rightTier, "asc")
        break
      case "playtime":
        comparison = compareNullableNumbers(
          leaderboardByMapId.get(left.id)?.total_playtime,
          leaderboardByMapId.get(right.id)?.total_playtime,
          sortDirection,
        )
        break
      case "avgPlaytime":
        comparison = compareNullableNumbers(
          leaderboardByMapId.get(left.id)?.average_playtime_per_player,
          leaderboardByMapId.get(right.id)?.average_playtime_per_player,
          sortDirection,
        )
        break
      case "nub":
        comparison = compareNullableNumbers(
          leaderboardByMapId.get(left.id)?.unique_nub_finishes,
          leaderboardByMapId.get(right.id)?.unique_nub_finishes,
          sortDirection,
        )
        break
      case "pro":
        comparison = compareNullableNumbers(
          leaderboardByMapId.get(left.id)?.unique_pro_finishes,
          leaderboardByMapId.get(right.id)?.unique_pro_finishes,
          sortDirection,
        )
        break
      case "proRatio":
        comparison = compareNullableNumbers(
          leaderboardByMapId.get(left.id)?.pro_nub_ratio,
          leaderboardByMapId.get(right.id)?.pro_nub_ratio,
          sortDirection,
        )
        break
      case "finishes":
        comparison = compareNullableNumbers(
          leaderboardByMapId.get(left.id)?.total_finishes,
          leaderboardByMapId.get(right.id)?.total_finishes,
          sortDirection,
        )
        break
      case "firstMed":
        comparison = compareNullableNumbers(
          leaderboardByMapId.get(left.id)?.median_first_completion_time,
          leaderboardByMapId.get(right.id)?.median_first_completion_time,
          sortDirection,
        )
        break
      case "updated":
        comparison = Date.parse(left.updated_on) - Date.parse(right.updated_on)
        break
      case "created":
        comparison = Date.parse(left.created_on) - Date.parse(right.created_on)
        break
      case "overall":
        comparison = compareNullableNumbers(
          leftReviewSummary?.overall_avg,
          rightReviewSummary?.overall_avg,
          sortDirection,
        )
        break
      case "gameplay":
        comparison = compareNullableNumbers(
          leftReviewSummary?.gameplay_avg,
          rightReviewSummary?.gameplay_avg,
          sortDirection,
        )
        break
      case "visuals":
        comparison = compareNullableNumbers(
          leftReviewSummary?.visuals_avg,
          rightReviewSummary?.visuals_avg,
          sortDirection,
        )
        break
      case "reviewCount":
        comparison = compareNullableNumbers(
          leftReviewSummary?.reviews_count,
          rightReviewSummary?.reviews_count,
          sortDirection,
        )
        break
      case "commentsCount":
        comparison = compareNullableNumbers(
          leftReviewSummary?.comments_count,
          rightReviewSummary?.comments_count,
          sortDirection,
        )
        break
      case "wr":
        comparison = compareNullableNumbers(
          wrTimeByMapId.get(left.id),
          wrTimeByMapId.get(right.id),
          sortDirection,
        )
        break
      case "bonus":
        comparison = (left.bonus_count ?? 0) - (right.bonus_count ?? 0)
        break
      case "skill":
        comparison =
          getMapSkillPercentage(left.name, selectedSkill) -
          getMapSkillPercentage(right.name, selectedSkill)
        break
      default:
        comparison = compareLocaleText(left.name, right.name)
        break
    }

    if (
      comparison === 0 &&
      (sortField === "overall" ||
        sortField === "gameplay" ||
        sortField === "visuals")
    ) {
      comparison = compareNullableNumbers(
        leftReviewSummary?.reviews_count,
        rightReviewSummary?.reviews_count,
        sortDirection,
      )
    }

    if (
      comparison === 0 &&
      (sortField === "overall" ||
        sortField === "gameplay" ||
        sortField === "visuals" ||
        sortField === "reviewCount")
    ) {
      comparison = compareNullableNumbers(
        leftReviewSummary?.comments_count,
        rightReviewSummary?.comments_count,
        sortDirection,
      )
    }

    if (comparison === 0 && sortField === "commentsCount") {
      comparison = compareNullableNumbers(
        leftReviewSummary?.reviews_count,
        rightReviewSummary?.reviews_count,
        sortDirection,
      )
    }

    if (comparison === 0) {
      comparison = compareLocaleText(left.name, right.name)
    }

    if (
      sortField === "overall" ||
      sortField === "gameplay" ||
      sortField === "visuals" ||
      sortField === "wr" ||
      sortField === "reviewCount" ||
      sortField === "commentsCount" ||
      sortField === "playtime" ||
      sortField === "avgPlaytime" ||
      sortField === "nub" ||
      sortField === "pro" ||
      sortField === "proRatio" ||
      sortField === "finishes" ||
      sortField === "firstMed"
    ) {
      return comparison
    }

    return sortDirection === "asc" ? comparison : -comparison
  })
}

function MapsCatalogPagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number
  totalPages: number
  onPageChange: (page: number) => void
}) {
  const { t } = useTranslation()
  const [pageInputValue, setPageInputValue] = useState(`${page}`)

  useEffect(() => {
    setPageInputValue(`${page}`)
  }, [page])

  const commitPageInputValue = () => {
    const nextValue = Number(pageInputValue)
    if (!Number.isFinite(nextValue)) {
      setPageInputValue(`${page}`)
      return
    }

    const nextPage = Math.min(Math.max(Math.trunc(nextValue), 1), totalPages)
    setPageInputValue(`${nextPage}`)
    onPageChange(nextPage)
  }

  return (
    <nav aria-label={t("maps.pagesAria")} className="flex items-center gap-x-1">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-8 w-8 p-0"
        onClick={() => onPageChange(1)}
        disabled={page === 1}
      >
        <span className="sr-only">{t("pagination.first")}</span>
        <ChevronsLeft className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-8 w-12 p-0"
        onClick={() => onPageChange(Math.max(1, page - 1))}
        disabled={page === 1}
      >
        <span className="sr-only">{t("pagination.previous")}</span>
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <Input
        type="number"
        inputMode="numeric"
        min={1}
        max={totalPages}
        value={pageInputValue}
        onChange={(event) => {
          setPageInputValue(event.target.value)
        }}
        onBlur={commitPageInputValue}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault()
            commitPageInputValue()
          }
        }}
        className="h-8 w-14 rounded-md border-border bg-muted px-2 text-center text-sm font-medium text-foreground [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        aria-label={t("pagination.currentPage", {
          page,
          pageCount: totalPages,
        })}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-8 w-12 p-0"
        onClick={() => onPageChange(Math.min(totalPages, page + 1))}
        disabled={page >= totalPages}
      >
        <span className="sr-only">{t("pagination.next")}</span>
        <ChevronRight className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-8 w-8 p-0"
        onClick={() => onPageChange(totalPages)}
        disabled={page >= totalPages}
      >
        <span className="sr-only">{t("pagination.last")}</span>
        <ChevronsRight className="h-4 w-4" />
      </Button>
    </nav>
  )
}

function DownloadCommandBlock({
  command,
  label,
}: {
  command: string
  label: string
}) {
  const { t } = useTranslation()
  const [, copyToClipboard] = useCopyToClipboard()

  const handleCopyCommand = async () => {
    const didCopy = await copyToClipboard(command)
    if (didCopy) {
      toast.success(t("maps.downloadDialog.commandCopied"), {
        description: label,
      })
      return
    }

    toast.error(t("common.copyFailed", { label }))
  }

  return (
    <div className="min-w-0 space-y-2">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <div className="flex min-w-0 items-start gap-2 rounded-md border border-[#5d5d5d] bg-[#3b3b3b] px-3 py-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
        <pre className="block min-w-0 flex-1 overflow-x-auto pb-1 font-mono text-[13px] leading-6 whitespace-pre text-[#d4d4d4] [scrollbar-color:rgba(212,212,212,0.45)_transparent] [scrollbar-width:thin]">
          <code>{command}</code>
        </pre>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="-mt-0.5 shrink-0 rounded-md text-[#cfcfcf] opacity-80 shadow-none hover:bg-white/8 hover:text-white hover:opacity-100 focus-visible:ring-white/20"
          aria-label={t("maps.downloadDialog.copyCommand", { label })}
          title={t("maps.downloadDialog.copyCommand", { label })}
          onClick={() => {
            void handleCopyCommand()
          }}
        >
          <Copy className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  )
}

function MapsDownloadDialog() {
  const { t } = useTranslation()

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" className="gap-2">
          <Download className="size-4" aria-hidden="true" />
          {t("maps.downloadDialog.button")}
        </Button>
      </DialogTrigger>
      <DialogContent className="min-w-0 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("maps.downloadDialog.title")}</DialogTitle>
          <DialogDescription>
            {t("maps.downloadDialog.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="min-w-0 space-y-4">
          <DownloadCommandBlock
            label={t("maps.downloadDialog.windowsLabel")}
            command={POWERSHELL_DOWNLOAD_COMMAND}
          />
          <DownloadCommandBlock
            label={t("maps.downloadDialog.linuxLabel")}
            command={POSIX_DOWNLOAD_COMMAND}
          />

          <p className="text-sm text-muted-foreground">
            {t("maps.downloadDialog.runFrom")}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function MapValidationButton({
  status,
  onToggle,
}: {
  status: MapValidationStatus
  onToggle: () => void
}) {
  const { t } = useTranslation()
  const isValidated = status === "validated"

  return (
    <button
      type="button"
      className={cn(
        "relative inline-flex size-8 items-center justify-center overflow-hidden rounded-md text-white shadow-xs transition-[background-color,box-shadow,transform] duration-300 ease-out outline-none hover:scale-105 active:scale-95 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        isValidated ? "bg-emerald-500" : "bg-red-500",
      )}
      aria-label={t(
        isValidated ? "maps.validatedStatusAria" : "maps.invalidStatusAria",
      )}
      aria-pressed={!isValidated}
      onClick={onToggle}
      title={t(
        isValidated ? "maps.validatedStatusAria" : "maps.invalidStatusAria",
      )}
    >
      <span
        key={status}
        aria-hidden="true"
        className={cn(
          "absolute inset-0 rounded-md opacity-35 motion-safe:animate-ping",
          isValidated ? "bg-emerald-300" : "bg-red-300",
        )}
      />
      <Globe
        className={cn(
          "relative size-4 transform-gpu transition-transform duration-300 ease-out",
          isValidated ? "rotate-0 scale-100" : "rotate-180 scale-90",
        )}
        aria-hidden="true"
      />
    </button>
  )
}

export function MapsCatalog() {
  const { t } = useTranslation()
  const { scope } = useScope()
  const [persistedState] = useState(readPersistedMapsCatalogState)
  const [searchInput, setSearchInput] = useState(
    typeof persistedState.searchInput === "string"
      ? persistedState.searchInput
      : "",
  )
  const deferredSearch = useDeferredValue(searchInput)
  const [sortField, setSortField] = useState<MapsSortField>(
    isMapsSortField(persistedState.sortField)
      ? persistedState.sortField
      : "name",
  )
  const [sortDirection, setSortDirection] = useState<MapsSortDirection>(
    persistedState.sortDirection === "desc" ? "desc" : "asc",
  )
  const [selectedSkill, setSelectedSkill] = useState<SortableSkillKey>(
    isSortableSkillKey(persistedState.selectedSkill)
      ? persistedState.selectedSkill
      : "ladder",
  )
  const [selectedReviewSort, setSelectedReviewSort] = useState<ReviewSortField>(
    isReviewSortField(persistedState.selectedReviewSort)
      ? persistedState.selectedReviewSort
      : "overall",
  )
  const [selectedTier, setSelectedTier] = useState<TierSelectorValue>(
    isTierSelectorValue(persistedState.selectedTier)
      ? persistedState.selectedTier
      : "all",
  )
  const [minimumTier, setMinimumTier] = useState<TierSelectorValue>(
    isTierSelectorValue(persistedState.minimumTier)
      ? persistedState.minimumTier
      : "all",
  )
  const [maximumTier, setMaximumTier] = useState<TierSelectorValue>(
    isTierSelectorValue(persistedState.maximumTier)
      ? persistedState.maximumTier
      : "all",
  )
  const [withBonusOnly, setWithBonusOnly] = useState(
    persistedState.withBonusOnly === true,
  )
  const [validationStatus, setValidationStatus] = useState<MapValidationStatus>(
    isMapValidationStatus(persistedState.validationStatus)
      ? persistedState.validationStatus
      : "validated",
  )
  const [showFilters, setShowFilters] = useState(false)
  const [mapFilters, setMapFilters] = useState<MapFilterValues>(() => ({
    ...EMPTY_MAP_FILTERS,
    ...(persistedState.mapFilters ?? {}),
  }))
  const [page, setPage] = useState(
    typeof persistedState.page === "number" && persistedState.page >= 1
      ? Math.trunc(persistedState.page)
      : 1,
  )

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        MAPS_CATALOG_STORAGE_KEY,
        JSON.stringify({
          searchInput,
          sortField,
          sortDirection,
          selectedSkill,
          selectedReviewSort,
          selectedTier,
          minimumTier,
          maximumTier,
          withBonusOnly,
          validationStatus,
          mapFilters,
          page,
        } satisfies PersistedMapsCatalogState),
      )
    } catch {
      // Session storage can be unavailable in private browsing or restricted contexts.
    }
  }, [
    mapFilters,
    maximumTier,
    minimumTier,
    page,
    searchInput,
    selectedReviewSort,
    selectedSkill,
    selectedTier,
    sortDirection,
    sortField,
    validationStatus,
    withBonusOnly,
  ])

  const requestedValidatedMaps = validationStatus === "validated"
  const normalizedDeferredSearch = deferredSearch.trim().toLowerCase()
  const mapsQuery = useQuery({
    queryKey: ["maps", "catalog", scope, validationStatus],
    queryFn: () =>
      MapsService.readMaps({
        offset: 0,
        limit: 10000,
        isValidated: requestedValidatedMaps,
        scope,
      }),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  })
  const validNameMatchCount = useMemo(() => {
    if (!requestedValidatedMaps || normalizedDeferredSearch === "") {
      return mapsQuery.data?.length ?? 0
    }

    return (mapsQuery.data ?? []).filter((map) =>
      map.name.toLowerCase().includes(normalizedDeferredSearch),
    ).length
  }, [mapsQuery.data, normalizedDeferredSearch, requestedValidatedMaps])
  const shouldCheckInvalidSearchMatches =
    requestedValidatedMaps &&
    normalizedDeferredSearch !== "" &&
    !mapsQuery.isLoading &&
    validNameMatchCount === 0
  const invalidSearchMapsQuery = useQuery({
    queryKey: ["maps", "catalog", scope, "invalid-search-fallback"],
    queryFn: () =>
      MapsService.readMaps({
        offset: 0,
        limit: 10000,
        isValidated: false,
        scope,
      }),
    enabled: shouldCheckInvalidSearchMatches,
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  })
  const invalidSearchNameMatchCount = useMemo(() => {
    if (!shouldCheckInvalidSearchMatches) {
      return 0
    }

    return (invalidSearchMapsQuery.data ?? []).filter((map) =>
      map.name.toLowerCase().includes(normalizedDeferredSearch),
    ).length
  }, [
    invalidSearchMapsQuery.data,
    normalizedDeferredSearch,
    shouldCheckInvalidSearchMatches,
  ])
  const showingInvalidSearchFallback =
    shouldCheckInvalidSearchMatches && invalidSearchNameMatchCount > 0
  const activeValidationStatus: MapValidationStatus =
    showingInvalidSearchFallback ? "invalid" : validationStatus
  const activeMaps = useMemo(
    () =>
      showingInvalidSearchFallback
        ? (invalidSearchMapsQuery.data ?? [])
        : (mapsQuery.data ?? []),
    [invalidSearchMapsQuery.data, mapsQuery.data, showingInvalidSearchFallback],
  )
  const wrsQuery = useQuery({
    queryKey: ["maps", "catalog", "wrs", scope, "NUB"],
    queryFn: () =>
      MapsService.readMapWrs({
        scope,
        type: "NUB",
      }),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  })
  const mapLeaderboardQuery = useQuery({
    queryKey: ["leaderboards", "maps", "catalog", scope],
    queryFn: () => LeaderboardsService.readMapLeaderboard({ scope }),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  const searchableMaps = useMemo(
    () =>
      activeMaps.map((map) => ({
        map,
        normalizedName: map.name.toLowerCase(),
      })),
    [activeMaps],
  )

  const wrByMapId = useMemo(() => {
    const nextMap = new Map<number, MapWrPublic>()
    for (const record of wrsQuery.data ?? []) {
      if (!nextMap.has(record.map_id)) {
        nextMap.set(record.map_id, record)
      }
    }
    return nextMap
  }, [wrsQuery.data])

  const wrTimeByMapId = useMemo(() => {
    const nextMap = new Map<number, number>()
    for (const [mapId, record] of wrByMapId) {
      nextMap.set(mapId, record.time)
    }
    return nextMap
  }, [wrByMapId])

  const leaderboardByMapId = useMemo(() => {
    const next = new Map<number, MapLeaderboardEntryPublic>()
    for (const entry of mapLeaderboardQuery.data?.data ?? []) {
      next.set(entry.map.id, entry)
    }
    return next
  }, [mapLeaderboardQuery.data])

  const filteredMaps = useMemo(() => {
    const normalizedQuery = normalizedDeferredSearch
    const wrMin = parseWrTime(mapFilters.wrMin)
    const wrMax = parseWrTime(mapFilters.wrMax)
    const createdMin = parseDateBound(mapFilters.createdMin)
    const createdMax = parseDateBound(mapFilters.createdMax, true)
    const updatedMin = parseDateBound(mapFilters.updatedMin)
    const updatedMax = parseDateBound(mapFilters.updatedMax, true)
    const ratingMin = parseNumber(mapFilters.ratingMin)
    const ratingMax = parseNumber(mapFilters.ratingMax)
    const reviewsMin = parseNumber(mapFilters.reviewsMin)
    const reviewsMax = parseNumber(mapFilters.reviewsMax)
    const commentsMin = parseNumber(mapFilters.commentsMin)
    const commentsMax = parseNumber(mapFilters.commentsMax)
    const hasWrFilter = hasValue(mapFilters.wrMin) || hasValue(mapFilters.wrMax)
    const hasCreatedFilter =
      hasValue(mapFilters.createdMin) || hasValue(mapFilters.createdMax)
    const hasUpdatedFilter =
      hasValue(mapFilters.updatedMin) || hasValue(mapFilters.updatedMax)
    const hasRatingFilter =
      hasValue(mapFilters.ratingMin) || hasValue(mapFilters.ratingMax)
    const hasReviewsFilter =
      hasValue(mapFilters.reviewsMin) || hasValue(mapFilters.reviewsMax)
    const hasCommentsFilter =
      hasValue(mapFilters.commentsMin) || hasValue(mapFilters.commentsMax)
    const wrFilterValid =
      !isInvalidValue(mapFilters.wrMin, parseWrTime) &&
      !isInvalidValue(mapFilters.wrMax, parseWrTime) &&
      !isRangeReversed(mapFilters.wrMin, mapFilters.wrMax, parseWrTime)
    const dateFilterValid = (min: string, max: string) => {
      const dateParser = (value: string) => parseDateBound(value)
      return (
        !isInvalidValue(min, dateParser) &&
        !isInvalidValue(max, dateParser) &&
        !isRangeReversed(min, max, dateParser)
      )
    }
    const numberFilterValid = (min: string, max: string) =>
      !isInvalidValue(min, parseNumber) &&
      !isInvalidValue(max, parseNumber) &&
      !isRangeReversed(min, max, parseNumber)

    return searchableMaps.flatMap(({ map, normalizedName }) => {
      if (normalizedQuery !== "" && !normalizedName.includes(normalizedQuery)) {
        return []
      }

      const activeTier = normalizeTierValue(getMapTierForScope(map, scope))
      const effectiveMinimumTier =
        selectedTier !== "all"
          ? Number(selectedTier)
          : minimumTier === "all"
            ? null
            : Number(minimumTier)
      const effectiveMaximumTier =
        selectedTier !== "all"
          ? Number(selectedTier)
          : maximumTier === "all"
            ? null
            : Number(maximumTier)
      if (
        (selectedTier !== "all" ||
          minimumTier !== "all" ||
          maximumTier !== "all") &&
        (selectedTier !== "all" ||
          minimumTier === "all" ||
          maximumTier === "all" ||
          Number(minimumTier) <= Number(maximumTier)) &&
        (activeTier === null ||
          (effectiveMinimumTier !== null &&
            activeTier < effectiveMinimumTier) ||
          (effectiveMaximumTier !== null && activeTier > effectiveMaximumTier))
      ) {
        return []
      }

      if (withBonusOnly && (map.bonus_count ?? 0) <= 0) {
        return []
      }

      const wrTime = wrTimeByMapId.get(map.id)
      if (
        hasWrFilter &&
        wrFilterValid &&
        (wrTime === undefined ||
          (wrMin !== null && wrTime < wrMin) ||
          (wrMax !== null && wrTime > wrMax))
      ) {
        return []
      }

      const createdAt = Date.parse(map.created_on)
      if (
        hasCreatedFilter &&
        dateFilterValid(mapFilters.createdMin, mapFilters.createdMax) &&
        ((createdMin !== null && createdAt < createdMin) ||
          (createdMax !== null && createdAt > createdMax))
      ) {
        return []
      }

      const updatedAt = Date.parse(map.updated_on)
      if (
        hasUpdatedFilter &&
        dateFilterValid(mapFilters.updatedMin, mapFilters.updatedMax) &&
        ((updatedMin !== null && updatedAt < updatedMin) ||
          (updatedMax !== null && updatedAt > updatedMax))
      ) {
        return []
      }

      const reviewSummary = map.review_summary
      const overallRating = reviewSummary?.overall_avg
      const reviewsCount = reviewSummary?.reviews_count
      const commentsCount = reviewSummary?.comments_count
      if (
        (hasRatingFilter &&
          numberFilterValid(mapFilters.ratingMin, mapFilters.ratingMax) &&
          (overallRating === undefined ||
            overallRating === null ||
            (ratingMin !== null && overallRating < ratingMin) ||
            (ratingMax !== null && overallRating > ratingMax))) ||
        (hasReviewsFilter &&
          numberFilterValid(mapFilters.reviewsMin, mapFilters.reviewsMax) &&
          (reviewsCount === undefined ||
            reviewsCount === null ||
            (reviewsMin !== null && reviewsCount < reviewsMin) ||
            (reviewsMax !== null && reviewsCount > reviewsMax))) ||
        (hasCommentsFilter &&
          numberFilterValid(mapFilters.commentsMin, mapFilters.commentsMax) &&
          (commentsCount === undefined ||
            commentsCount === null ||
            (commentsMin !== null && commentsCount < commentsMin) ||
            (commentsMax !== null && commentsCount > commentsMax)))
      ) {
        return []
      }

      return map
    })
  }, [
    mapFilters,
    maximumTier,
    minimumTier,
    normalizedDeferredSearch,
    scope,
    searchableMaps,
    selectedTier,
    withBonusOnly,
    wrTimeByMapId,
  ])

  const mapFilterErrors = useMemo(() => {
    const errors: string[] = []
    if (
      selectedTier === "all" &&
      minimumTier !== "all" &&
      maximumTier !== "all" &&
      Number(minimumTier) > Number(maximumTier)
    ) {
      errors.push(t("maps.invalidRange"))
    }
    if (
      isInvalidValue(mapFilters.wrMin, parseWrTime) ||
      isInvalidValue(mapFilters.wrMax, parseWrTime)
    ) {
      errors.push(t("maps.invalidWrTime"))
    } else if (
      isRangeReversed(mapFilters.wrMin, mapFilters.wrMax, parseWrTime)
    ) {
      errors.push(t("maps.invalidRange"))
    }

    const dateParser = (value: string) => parseDateBound(value)
    for (const [min, max] of [
      [mapFilters.createdMin, mapFilters.createdMax],
      [mapFilters.updatedMin, mapFilters.updatedMax],
    ]) {
      if (isInvalidValue(min, dateParser) || isInvalidValue(max, dateParser)) {
        errors.push(t("maps.invalidDate"))
      } else if (isRangeReversed(min, max, dateParser)) {
        errors.push(t("maps.invalidRange"))
      }
    }

    for (const [min, max] of [
      [mapFilters.ratingMin, mapFilters.ratingMax],
      [mapFilters.reviewsMin, mapFilters.reviewsMax],
      [mapFilters.commentsMin, mapFilters.commentsMax],
    ]) {
      if (
        isInvalidValue(min, parseNumber) ||
        isInvalidValue(max, parseNumber)
      ) {
        errors.push(t("maps.invalidNumber"))
      } else if (isRangeReversed(min, max, parseNumber)) {
        errors.push(t("maps.invalidRange"))
      }
    }

    return [...new Set(errors)]
  }, [mapFilters, maximumTier, minimumTier, selectedTier, t])

  const activeFilterCount = [
    selectedTier !== "all",
    minimumTier !== "all",
    maximumTier !== "all",
    withBonusOnly,
    ...Object.values(mapFilters).map(hasValue),
  ].filter(Boolean).length

  function updateMapFilter(key: keyof MapFilterValues, value: string) {
    startTransition(() => {
      setMapFilters((current) => ({ ...current, [key]: value }))
      setPage(1)
    })
  }

  function clearMapFilters() {
    startTransition(() => {
      setSelectedTier("all")
      setMinimumTier("all")
      setMaximumTier("all")
      setWithBonusOnly(false)
      setMapFilters(EMPTY_MAP_FILTERS)
      setPage(1)
    })
  }

  const sortedMaps = useMemo(
    () =>
      sortMaps(
        filteredMaps,
        sortField,
        sortDirection,
        scope,
        selectedSkill,
        wrTimeByMapId,
        leaderboardByMapId,
      ),
    [
      filteredMaps,
      scope,
      selectedSkill,
      sortDirection,
      sortField,
      wrTimeByMapId,
      leaderboardByMapId,
    ],
  )

  const totalMaps = activeMaps.length
  const totalPages = Math.max(1, Math.ceil(sortedMaps.length / PAGE_SIZE))

  useEffect(() => {
    if (page <= totalPages) {
      return
    }

    startTransition(() => {
      setPage(totalPages)
    })
  }, [page, totalPages])

  const visibleMaps = useMemo(() => {
    const startIndex = (page - 1) * PAGE_SIZE
    return sortedMaps.slice(startIndex, startIndex + PAGE_SIZE)
  }, [page, sortedMaps])

  const keyboardPaginationRef = useKeyboardPagination({
    enabled: totalPages > 1,
    canPrevious: page > 1,
    canNext: page < totalPages,
    onPrevious: () => {
      startTransition(() => {
        setPage((currentPage) => Math.max(1, currentPage - 1))
      })
    },
    onNext: () => {
      startTransition(() => {
        setPage((currentPage) => Math.min(totalPages, currentPage + 1))
      })
    },
  })

  if (mapsQuery.isLoading) {
    return <PendingMaps />
  }

  if (mapsQuery.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t("errors.mapsFailed")}</AlertTitle>
        <AlertDescription className="gap-3">
          <p>{t("maps.requestFailed")}</p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void mapsQuery.refetch()
            }}
          >
            {t("common.retry")}
          </Button>
        </AlertDescription>
      </Alert>
    )
  }

  function handleSortChange(nextSortField: MapsSortOption) {
    startTransition(() => {
      setPage(1)
      if (nextSortField === "skill" || nextSortField === "bonus") {
        setSortField(nextSortField)
        setSortDirection("desc")
        return
      }

      if (nextSortField === "wr") {
        if (sortField === "wr") {
          setSortDirection((currentDirection) =>
            currentDirection === "asc" ? "desc" : "asc",
          )
          return
        }

        setSortField("wr")
        setSortDirection("asc")
        return
      }

      if (nextSortField === "review") {
        if (isReviewSortField(sortField)) {
          setSortDirection((currentDirection) =>
            currentDirection === "asc" ? "desc" : "asc",
          )
          return
        }

        setSortField(selectedReviewSort)
        setSortDirection("desc")
        return
      }

      if (nextSortField === "metrics") {
        if (METRIC_SORT_OPTIONS.some((option) => option.value === sortField)) {
          setSortDirection((currentDirection) =>
            currentDirection === "asc" ? "desc" : "asc",
          )
          return
        }
        setSortField("playtime")
        setSortDirection("desc")
        return
      }

      if (nextSortField === sortField) {
        setSortDirection((currentDirection) =>
          currentDirection === "asc" ? "desc" : "asc",
        )
        return
      }

      setSortField(nextSortField)
      setSortDirection("asc")
    })
  }

  function handleSkillSortSelection(nextSkill: SortableSkillKey) {
    startTransition(() => {
      setPage(1)
      setSelectedSkill(nextSkill)
      setSortField("skill")
      setSortDirection("desc")
    })
  }

  function handleMetricSortSelection(nextMetric: MetricSortField) {
    startTransition(() => {
      setPage(1)
      if (sortField === nextMetric) {
        setSortDirection((currentDirection) =>
          currentDirection === "asc" ? "desc" : "asc",
        )
        return
      }
      setSortField(nextMetric)
      setSortDirection("desc")
    })
  }

  function handleReviewSortSelection(nextReviewSort: ReviewSortField) {
    startTransition(() => {
      setPage(1)
      setSelectedReviewSort(nextReviewSort)

      if (sortField === nextReviewSort) {
        setSortDirection((currentDirection) =>
          currentDirection === "asc" ? "desc" : "asc",
        )
        return
      }

      setSortField(nextReviewSort)
      setSortDirection("desc")
    })
  }

  function handlePageChange(nextPage: number) {
    startTransition(() => {
      setPage(Math.min(totalPages, Math.max(1, nextPage)))
    })
  }

  return (
    <div ref={keyboardPaginationRef} className="space-y-8">
      <section className="rounded-2xl border border-border/70 bg-card/60 p-4 shadow-sm backdrop-blur-sm sm:p-5">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative block w-full min-w-0 sm:flex-1 lg:w-[16rem] lg:flex-none">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={searchInput}
                  onChange={(event) => {
                    setSearchInput(event.target.value)
                    startTransition(() => {
                      setPage(1)
                    })
                  }}
                  placeholder={t("maps.searchPlaceholder")}
                  aria-label={t("maps.searchAria")}
                  className="pl-9"
                />
              </div>
              <TierSelector
                value={selectedTier}
                onValueChange={(nextValue) => {
                  startTransition(() => {
                    setSelectedTier(nextValue)
                    setPage(1)
                  })
                }}
                triggerClassName="w-auto"
                ariaLabel={t("maps.filterTier")}
              />
              <MapValidationButton
                status={activeValidationStatus}
                onToggle={() => {
                  startTransition(() => {
                    setValidationStatus((currentValue) =>
                      currentValue === "validated" ? "invalid" : "validated",
                    )
                    setPage(1)
                  })
                }}
              />
              <Button
                type="button"
                variant="outline"
                className={cn(
                  "gap-2",
                  activeFilterCount > 0 &&
                    "border-primary/50 bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary",
                )}
                aria-expanded={showFilters}
                aria-controls="maps-filter-panel"
                onClick={() => {
                  setShowFilters((currentValue) => !currentValue)
                }}
              >
                <Filter className="size-4" />
                <span>
                  {showFilters ? t("maps.hideFilters") : t("maps.showFilters")}
                </span>
                {activeFilterCount > 0 ? (
                  <span className="rounded-full bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">
                    {activeFilterCount}
                  </span>
                ) : null}
              </Button>
            </div>

            <MapsDownloadDialog />
          </div>

          {showFilters ? (
            <div
              id="maps-filter-panel"
              className="space-y-4 rounded-xl border border-border/70 bg-muted/20 p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-sm font-semibold">
                  {t("maps.filterTitle")}
                </h2>
                {activeFilterCount > 0 ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="gap-2 text-muted-foreground"
                    onClick={clearMapFilters}
                  >
                    <SearchX className="size-4" />
                    {t("maps.clearFilters")}
                  </Button>
                ) : null}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className={cn(
                    "flex h-9 w-fit items-center rounded-md border border-border/70 bg-background px-3 text-sm font-medium text-muted-foreground shadow-xs transition-colors outline-none hover:text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
                    withBonusOnly &&
                      "border-primary/50 bg-primary/10 text-primary hover:text-primary",
                  )}
                  aria-label={t("maps.withBonusAria")}
                  aria-pressed={withBonusOnly}
                  onClick={() => {
                    startTransition(() => {
                      setWithBonusOnly((currentValue) => !currentValue)
                      setPage(1)
                    })
                  }}
                >
                  <span>{t("maps.withBonus")}</span>
                </button>
              </div>

              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <div className="space-y-2">
                  <Label>{t("maps.filterFields.tier")}</Label>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <TierSelector
                        value={minimumTier}
                        onValueChange={(nextValue) => {
                          startTransition(() => {
                            setMinimumTier(nextValue)
                            setPage(1)
                          })
                        }}
                        allLabel={t("maps.filterMin")}
                        showAllLabelInTrigger
                        triggerClassName="w-full"
                        ariaLabel={t("maps.minimumTierAria")}
                      />
                    </div>
                    <div>
                      <TierSelector
                        value={maximumTier}
                        onValueChange={(nextValue) => {
                          startTransition(() => {
                            setMaximumTier(nextValue)
                            setPage(1)
                          })
                        }}
                        allLabel={t("maps.filterMax")}
                        showAllLabelInTrigger
                        triggerClassName="w-full"
                        ariaLabel={t("maps.maximumTierAria")}
                      />
                    </div>
                  </div>
                </div>
                <RangeInputs
                  id="maps-filter-wr"
                  label={t("maps.filterFields.wrTime")}
                  min={mapFilters.wrMin}
                  max={mapFilters.wrMax}
                  onMinChange={(value) => updateMapFilter("wrMin", value)}
                  onMaxChange={(value) => updateMapFilter("wrMax", value)}
                  minPlaceholder={t("maps.filterMin")}
                  maxPlaceholder={t("maps.filterMax")}
                  type="text"
                  inputMode="text"
                />
                <RangeInputs
                  id="maps-filter-created"
                  label={t("maps.filterFields.createdAt")}
                  min={mapFilters.createdMin}
                  max={mapFilters.createdMax}
                  onMinChange={(value) => updateMapFilter("createdMin", value)}
                  onMaxChange={(value) => updateMapFilter("createdMax", value)}
                  minPlaceholder={t("maps.filterMin")}
                  maxPlaceholder={t("maps.filterMax")}
                  type="date"
                  inputMode="text"
                />
                <RangeInputs
                  id="maps-filter-updated"
                  label={t("maps.filterFields.updatedAt")}
                  min={mapFilters.updatedMin}
                  max={mapFilters.updatedMax}
                  onMinChange={(value) => updateMapFilter("updatedMin", value)}
                  onMaxChange={(value) => updateMapFilter("updatedMax", value)}
                  minPlaceholder={t("maps.filterMin")}
                  maxPlaceholder={t("maps.filterMax")}
                  type="date"
                  inputMode="text"
                />
                <RangeInputs
                  id="maps-filter-rating"
                  label={t("maps.filterFields.overallRating")}
                  min={mapFilters.ratingMin}
                  max={mapFilters.ratingMax}
                  onMinChange={(value) => updateMapFilter("ratingMin", value)}
                  onMaxChange={(value) => updateMapFilter("ratingMax", value)}
                  minPlaceholder={t("maps.filterMin")}
                  maxPlaceholder={t("maps.filterMax")}
                />
                <RangeInputs
                  id="maps-filter-reviews"
                  label={t("maps.filterFields.reviewCount")}
                  min={mapFilters.reviewsMin}
                  max={mapFilters.reviewsMax}
                  onMinChange={(value) => updateMapFilter("reviewsMin", value)}
                  onMaxChange={(value) => updateMapFilter("reviewsMax", value)}
                  minPlaceholder={t("maps.filterMin")}
                  maxPlaceholder={t("maps.filterMax")}
                  inputMode="numeric"
                />
                <RangeInputs
                  id="maps-filter-comments"
                  label={t("maps.filterFields.commentsCount")}
                  min={mapFilters.commentsMin}
                  max={mapFilters.commentsMax}
                  onMinChange={(value) => updateMapFilter("commentsMin", value)}
                  onMaxChange={(value) => updateMapFilter("commentsMax", value)}
                  minPlaceholder={t("maps.filterMin")}
                  maxPlaceholder={t("maps.filterMax")}
                  inputMode="numeric"
                />
              </div>

              {mapFilterErrors.length > 0 ? (
                <p className="text-sm text-destructive" role="alert">
                  {mapFilterErrors.join(" ")}
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <fieldset className="min-w-0 border-0 p-0">
              <legend className="sr-only">{t("maps.sortMaps")}</legend>
              <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
                {MAP_SORT_OPTIONS.map((option) => {
                  const isReviewOption = option.value === "review"
                  const isActive = isReviewOption
                    ? isReviewSortField(sortField)
                    : option.value === sortField
                  const activeDirection =
                    option.value === "skill" || option.value === "bonus"
                      ? "desc"
                      : isActive
                        ? sortDirection
                        : undefined

                  return (
                    <SortableMapOption
                      key={option.value}
                      active={isActive}
                      direction={isActive ? activeDirection : undefined}
                      label={t(option.labelKey)}
                      onClick={() => {
                        handleSortChange(option.value)
                      }}
                    />
                  )
                })}
              </div>
            </fieldset>

            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground lg:justify-end">
              <div className="font-medium tabular-nums">
                {formatNumber(sortedMaps.length)} / {formatNumber(totalMaps)}
              </div>
              <MapsCatalogPagination
                page={page}
                totalPages={totalPages}
                onPageChange={handlePageChange}
              />
            </div>
          </div>

          {isReviewSortField(sortField) ? (
            <fieldset className="min-w-0 border-0 p-0">
              <legend className="sr-only">{t("maps.sortMapsByReview")}</legend>
              <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
                {REVIEW_SORT_OPTIONS.map((option) => (
                  <SortableMapOption
                    key={option.value}
                    active={sortField === option.value}
                    direction={
                      sortField === option.value ? sortDirection : undefined
                    }
                    label={t(option.labelKey)}
                    onClick={() => {
                      handleReviewSortSelection(option.value)
                    }}
                  />
                ))}
              </div>
            </fieldset>
          ) : null}

          {METRIC_SORT_OPTIONS.some((option) => option.value === sortField) ? (
            <fieldset className="min-w-0 border-0 p-0">
              <legend className="sr-only">
                {t("maps.sortOptions.metrics")}
              </legend>
              <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
                {METRIC_SORT_OPTIONS.map((option) => (
                  <SortableMapOption
                    key={option.value}
                    active={sortField === option.value}
                    direction={
                      sortField === option.value ? sortDirection : undefined
                    }
                    label={t(option.labelKey)}
                    tooltip={
                      option.value === "nub"
                        ? t("maps.sortOptions.nubTooltip")
                        : option.value === "pro"
                          ? t("maps.sortOptions.proTooltip")
                          : undefined
                    }
                    onClick={() => {
                      handleMetricSortSelection(option.value)
                    }}
                  />
                ))}
              </div>
            </fieldset>
          ) : null}

          {sortField === "skill" ? (
            <fieldset className="min-w-0 border-0 p-0">
              <legend className="sr-only">{t("maps.sortMapsBySkill")}</legend>
              <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
                {MAP_SORTABLE_SKILLS.map((skill) => {
                  const isActive = skill.key === selectedSkill

                  return (
                    <Button
                      key={skill.key}
                      type="button"
                      variant="ghost"
                      className={cn(
                        "-ml-3 h-8 px-3 text-left text-sm",
                        isActive ? "text-foreground" : "text-muted-foreground",
                      )}
                      aria-pressed={isActive}
                      onClick={() => {
                        handleSkillSortSelection(skill.key)
                      }}
                    >
                      <span
                        className="size-2 rounded-full"
                        style={{ backgroundColor: skill.color }}
                      />
                      <span>{skill.label}</span>
                      {isActive ? <ArrowDown className="ml-2 size-4" /> : null}
                    </Button>
                  )
                })}
              </div>
            </fieldset>
          ) : null}
        </div>
      </section>

      {visibleMaps.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border px-6 py-16 text-center">
          <h2 className="text-lg font-semibold">{t("maps.noResultsTitle")}</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {t("maps.noResultsBody")}
          </p>
        </div>
      ) : (
        <section className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {visibleMaps.map((map) => (
            <MapCard
              key={map.id}
              activeTier={getMapTierForScope(map, scope)}
              map={map}
              wrRecord={wrByMapId.get(map.id) ?? null}
              wrLoading={wrsQuery.isLoading}
              leaderboardEntry={leaderboardByMapId.get(map.id) ?? null}
              leaderboardSortField={sortField}
            />
          ))}
        </section>
      )}
    </div>
  )
}
