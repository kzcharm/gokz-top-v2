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
  Search,
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

import { type MapPublic, MapsService, type MapWrPublic } from "@/client"
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
  { labelKey: "maps.sortOptions.bonus", value: "bonus" },
  { labelKey: "maps.sortOptions.skill", value: "skill" },
] as const

const REVIEW_SORT_OPTIONS = [
  { labelKey: "maps.sortOptions.overall", value: "overall" },
  { labelKey: "maps.sortOptions.gameplay", value: "gameplay" },
  { labelKey: "maps.sortOptions.visuals", value: "visuals" },
  { labelKey: "maps.sortOptions.reviewCount", value: "reviewCount" },
  { labelKey: "maps.sortOptions.commentsCount", value: "commentsCount" },
] as const

type MapsSortOption = (typeof MAP_SORT_OPTIONS)[number]["value"]
type ReviewSortField = (typeof REVIEW_SORT_OPTIONS)[number]["value"]
type MapsSortField = Exclude<MapsSortOption, "review"> | ReviewSortField
type MapsSortDirection = "asc" | "desc"
type SortableSkillKey = Exclude<MapSkillKey, "unknown">

function isReviewSortField(value: MapsSortField): value is ReviewSortField {
  return REVIEW_SORT_OPTIONS.some((option) => option.value === value)
}

function SortableMapOption({
  active,
  direction,
  label,
  onClick,
}: {
  active: boolean
  direction?: MapsSortDirection
  label: string
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
      <span>{label}</span>
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
      sortField === "commentsCount"
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

export function MapsCatalog() {
  const { t } = useTranslation()
  const { scope } = useScope()
  const [searchInput, setSearchInput] = useState("")
  const deferredSearch = useDeferredValue(searchInput)
  const [sortField, setSortField] = useState<MapsSortField>("name")
  const [sortDirection, setSortDirection] = useState<MapsSortDirection>("asc")
  const [selectedSkill, setSelectedSkill] = useState<SortableSkillKey>("ladder")
  const [selectedReviewSort, setSelectedReviewSort] =
    useState<ReviewSortField>("overall")
  const [selectedTier, setSelectedTier] = useState<TierSelectorValue>("all")
  const [withBonusOnly, setWithBonusOnly] = useState(false)
  const [page, setPage] = useState(1)

  const mapsQuery = useQuery({
    queryKey: ["maps", "catalog", scope],
    queryFn: () =>
      MapsService.readMaps({
        offset: 0,
        limit: 10000,
        isValidated: true,
        scope,
      }),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  })
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

  const searchableMaps = useMemo(
    () =>
      (mapsQuery.data ?? []).map((map) => ({
        map,
        normalizedName: map.name.toLowerCase(),
      })),
    [mapsQuery.data],
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

  const filteredMaps = useMemo(() => {
    const normalizedQuery = deferredSearch.trim().toLowerCase()
    return searchableMaps.flatMap(({ map, normalizedName }) => {
      if (normalizedQuery !== "" && !normalizedName.includes(normalizedQuery)) {
        return []
      }

      if (selectedTier !== "all") {
        const activeTier = normalizeTierValue(getMapTierForScope(map, scope))
        if (activeTier !== Number(selectedTier)) {
          return []
        }
      }

      if (withBonusOnly && (map.bonus_count ?? 0) <= 0) {
        return []
      }

      return map
    })
  }, [deferredSearch, scope, searchableMaps, selectedTier, withBonusOnly])

  const sortedMaps = useMemo(
    () =>
      sortMaps(
        filteredMaps,
        sortField,
        sortDirection,
        scope,
        selectedSkill,
        wrTimeByMapId,
      ),
    [
      filteredMaps,
      scope,
      selectedSkill,
      sortDirection,
      sortField,
      wrTimeByMapId,
    ],
  )

  const totalMaps = mapsQuery.data?.length ?? 0
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
              <div className="relative block w-full min-w-0 sm:flex-1 lg:max-w-sm">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={searchInput}
                  onChange={(event) => {
                    startTransition(() => {
                      setSearchInput(event.target.value)
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

            <MapsDownloadDialog />
          </div>

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
            />
          ))}
        </section>
      )}
    </div>
  )
}
