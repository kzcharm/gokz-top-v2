import { useQuery } from "@tanstack/react-query"
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Search } from "lucide-react"
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
} from "react"

import { type MapPublic, MapsService, type MapWrPublic } from "@/client"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { useKeyboardPagination } from "@/components/Common/WASDNavigation"
import { MapCard } from "@/components/Maps/MapCard"
import {
  getMapSkillPercentage,
  MAP_SORTABLE_SKILLS,
  type MapSkillKey,
} from "@/components/Maps/map-utils"
import { PendingMaps } from "@/components/Maps/PendingMaps"
import { normalizeTierValue } from "@/components/Servers/tier"
import { type AppScope, useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 24

const MAP_SORT_OPTIONS = [
  { label: "Name", value: "name" },
  { label: "Tier", value: "tier" },
  { label: "Created", value: "created" },
  { label: "Updated", value: "updated" },
  { label: "WR", value: "wr" },
  { label: "Review", value: "review" },
  { label: "Skill", value: "skill" },
] as const

const REVIEW_SORT_OPTIONS = [
  { label: "Overall", value: "overall" },
  { label: "Gameplay", value: "gameplay" },
  { label: "Visuals", value: "visuals" },
  { label: "Review Count", value: "reviewCount" },
  { label: "Comments Count", value: "commentsCount" },
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

function getMapTierForScope(map: MapPublic, scope: AppScope) {
  return map.tiers[scope]
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
        comparison = compareNullableNumbers(leftTier, rightTier, sortDirection)
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
      case "skill":
        comparison =
          getMapSkillPercentage(left.name, selectedSkill) -
          getMapSkillPercentage(right.name, selectedSkill)
        break
      default:
        comparison = left.name.localeCompare(right.name)
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
      comparison = left.name.localeCompare(right.name)
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

function getPageNumbers(currentPage: number, totalPages: number) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  }

  const pages = new Set([
    1,
    totalPages,
    currentPage - 1,
    currentPage,
    currentPage + 1,
  ])

  if (currentPage <= 3) {
    pages.add(2)
    pages.add(3)
  }

  if (currentPage >= totalPages - 2) {
    pages.add(totalPages - 1)
    pages.add(totalPages - 2)
  }

  return [...pages]
    .filter((page) => page >= 1 && page <= totalPages)
    .sort((left, right) => left - right)
}

export function MapsCatalog() {
  const { scope } = useScope()
  const [searchInput, setSearchInput] = useState("")
  const deferredSearch = useDeferredValue(searchInput)
  const [sortField, setSortField] = useState<MapsSortField>("name")
  const [sortDirection, setSortDirection] = useState<MapsSortDirection>("asc")
  const [selectedSkill, setSelectedSkill] = useState<SortableSkillKey>("ladder")
  const [selectedReviewSort, setSelectedReviewSort] =
    useState<ReviewSortField>("overall")
  const [selectedTier, setSelectedTier] = useState<TierSelectorValue>("all")
  const [page, setPage] = useState(1)

  const mapsQuery = useQuery({
    queryKey: ["maps", "catalog"],
    queryFn: () =>
      MapsService.readMaps({ offset: 0, limit: 10000, isValidated: true }),
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

  useEffect(() => {
    startTransition(() => {
      setPage(1)
    })
  }, [])

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
    return (mapsQuery.data ?? []).filter((map) => {
      if (
        normalizedQuery !== "" &&
        !map.name.toLowerCase().includes(normalizedQuery)
      ) {
        return false
      }

      if (selectedTier !== "all") {
        const activeTier = normalizeTierValue(getMapTierForScope(map, scope))
        if (activeTier !== Number(selectedTier)) {
          return false
        }
      }

      return true
    })
  }, [deferredSearch, mapsQuery.data, scope, selectedTier])

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

  const pageNumbers = useMemo(
    () => getPageNumbers(page, totalPages),
    [page, totalPages],
  )
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
        <AlertTitle>Unable to load maps</AlertTitle>
        <AlertDescription className="gap-3">
          <p>The catalog request failed. Try reloading the maps list.</p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void mapsQuery.refetch()
            }}
          >
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    )
  }

  function handleSortChange(nextSortField: MapsSortOption) {
    startTransition(() => {
      setPage(1)
      if (nextSortField === "skill") {
        setSortField("skill")
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

  return (
    <div ref={keyboardPaginationRef} className="space-y-8">
      <section className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">Maps</h1>

        <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
          <span>{totalMaps.toLocaleString()} maps loaded</span>
          <span aria-hidden="true" className="text-border">
            /
          </span>
          <span>{sortedMaps.length.toLocaleString()} maps visible</span>
          <span aria-hidden="true" className="text-border">
            /
          </span>
          <span>
            Page {page} of {totalPages}
          </span>
        </div>
      </section>

      <section className="rounded-2xl border border-border/70 bg-card/60 p-4 shadow-sm backdrop-blur-sm sm:p-5">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative block w-full min-w-0 sm:flex-1 lg:max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchInput}
                onChange={(event) => {
                  const nextValue = event.target.value
                  startTransition(() => {
                    setSearchInput(nextValue)
                  })
                }}
                placeholder="Search maps..."
                aria-label="Search maps by name"
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
              ariaLabel="Filter maps by tier"
            />
          </div>

          <fieldset className="min-w-0 border-0 p-0">
            <legend className="sr-only">Sort maps</legend>
            <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
              {MAP_SORT_OPTIONS.map((option) => {
                const isReviewOption = option.value === "review"
                const isActive = isReviewOption
                  ? isReviewSortField(sortField)
                  : option.value === sortField
                const activeDirection =
                  option.value === "skill"
                    ? "desc"
                    : isActive
                      ? sortDirection
                      : undefined

                return (
                  <SortableMapOption
                    key={option.value}
                    active={isActive}
                    direction={isActive ? activeDirection : undefined}
                    label={option.label}
                    onClick={() => {
                      handleSortChange(option.value)
                    }}
                  />
                )
              })}
            </div>
          </fieldset>

          {isReviewSortField(sortField) ? (
            <fieldset className="min-w-0 border-0 p-0">
              <legend className="sr-only">Sort maps by review</legend>
              <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
                {REVIEW_SORT_OPTIONS.map((option) => (
                  <SortableMapOption
                    key={option.value}
                    active={sortField === option.value}
                    direction={
                      sortField === option.value ? sortDirection : undefined
                    }
                    label={option.label}
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
              <legend className="sr-only">Sort maps by skill</legend>
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
          <h2 className="text-lg font-semibold">No maps match this search</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Try a different name filter to widen the catalog results.
          </p>
        </div>
      ) : (
        <>
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

          {totalPages > 1 ? (
            <nav
              aria-label="Maps pages"
              className="flex flex-wrap items-center justify-center gap-2"
            >
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  startTransition(() => {
                    setPage((currentPage) => Math.max(1, currentPage - 1))
                  })
                }}
                disabled={page === 1}
              >
                <ArrowLeft />
                Previous
              </Button>

              {pageNumbers.map((pageNumber, index) => {
                const previousPageNumber = pageNumbers[index - 1]
                const showGap =
                  previousPageNumber !== undefined &&
                  pageNumber - previousPageNumber > 1

                return (
                  <div
                    key={`page-${pageNumber}`}
                    className="flex items-center gap-2"
                  >
                    {showGap ? (
                      <span className="px-1 text-sm text-muted-foreground">
                        ...
                      </span>
                    ) : null}
                    <Button
                      type="button"
                      variant={pageNumber === page ? "default" : "outline"}
                      className="min-w-9 px-3"
                      aria-current={pageNumber === page ? "page" : undefined}
                      aria-label={`Go to page ${pageNumber}`}
                      onClick={() => {
                        startTransition(() => {
                          setPage(pageNumber)
                        })
                      }}
                    >
                      {pageNumber}
                    </Button>
                  </div>
                )
              })}

              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  startTransition(() => {
                    setPage((currentPage) =>
                      Math.min(totalPages, currentPage + 1),
                    )
                  })
                }}
                disabled={page === totalPages}
              >
                Next
                <ArrowRight />
              </Button>
            </nav>
          ) : null}
        </>
      )}
    </div>
  )
}
