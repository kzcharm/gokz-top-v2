import { useQuery } from "@tanstack/react-query"
import {
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { Filter, SearchX } from "lucide-react"
import { startTransition, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { LeaderboardsService, type MapLeaderboardEntryPublic } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import {
  getMapLeaderboardColumns,
  type MapLeaderboardSortField,
  type MapLeaderboardTableRow,
} from "@/components/Leaderboards/map-columns"
import type { AppScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { extractErrorMessage } from "@/utils"

type SortDirection = "asc" | "desc"

function compareNullableNumbers(
  left: number | null | undefined,
  right: number | null | undefined,
  direction: SortDirection,
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

function parseOptionalNumber(value: string) {
  if (value.trim() === "") {
    return null
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function sortMaps(
  rows: MapLeaderboardEntryPublic[],
  sortField: MapLeaderboardSortField,
  sortDirection: SortDirection,
) {
  return [...rows].sort((left, right) => {
    let comparison = 0

    switch (sortField) {
      case "name":
        comparison =
          sortDirection === "asc"
            ? left.map.name.localeCompare(right.map.name)
            : right.map.name.localeCompare(left.map.name)
        break
      case "tier":
        comparison = compareNullableNumbers(
          left.tier,
          right.tier,
          sortDirection,
        )
        break
      case "overall_avg":
        comparison = compareNullableNumbers(
          left.review_summary?.overall_avg,
          right.review_summary?.overall_avg,
          sortDirection,
        )
        break
      default:
        comparison = compareNullableNumbers(
          left[sortField],
          right[sortField],
          sortDirection,
        )
        break
    }

    if (comparison === 0 && sortField === "overall_avg") {
      comparison = compareNullableNumbers(
        left.review_summary?.comments_count,
        right.review_summary?.comments_count,
        "desc",
      )
    }

    if (comparison === 0) {
      comparison = left.map.name.localeCompare(right.map.name)
    }

    return comparison
  })
}

export function MapsLeaderboardTab({ scope }: { scope: AppScope }) {
  const { t } = useTranslation()
  const [selectedTier, setSelectedTier] = useState<TierSelectorValue>("all")
  const [minUniqueFinishes, setMinUniqueFinishes] = useState("")
  const [maxUniqueFinishes, setMaxUniqueFinishes] = useState("")
  const [minPlaytime, setMinPlaytime] = useState("")
  const [maxPlaytime, setMaxPlaytime] = useState("")
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [sorting, setSorting] = useState<SortingState>([
    { id: "unique_nub_finishes", desc: true },
  ])

  const mapsQuery = useQuery({
    queryKey: ["leaderboards", "maps", scope],
    queryFn: () => LeaderboardsService.readMapLeaderboard({ scope }),
    staleTime: 30_000,
  })

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    setSorting(next.slice(0, 1))
    setPageIndex(0)
  }

  const filteredRows = useMemo(() => {
    const minUnique = parseOptionalNumber(minUniqueFinishes)
    const maxUnique = parseOptionalNumber(maxUniqueFinishes)
    const minTotalPlaytime = parseOptionalNumber(minPlaytime)
    const maxTotalPlaytime = parseOptionalNumber(maxPlaytime)

    return (mapsQuery.data?.data ?? []).filter((row) => {
      if (selectedTier !== "all" && row.tier !== Number(selectedTier)) {
        return false
      }
      if (minUnique !== null && row.unique_nub_finishes < minUnique) {
        return false
      }
      if (maxUnique !== null && row.unique_nub_finishes > maxUnique) {
        return false
      }
      if (minTotalPlaytime !== null && row.total_playtime < minTotalPlaytime) {
        return false
      }
      if (maxTotalPlaytime !== null && row.total_playtime > maxTotalPlaytime) {
        return false
      }
      return true
    })
  }, [
    mapsQuery.data,
    maxPlaytime,
    maxUniqueFinishes,
    minPlaytime,
    minUniqueFinishes,
    selectedTier,
  ])

  const sortField = useMemo<MapLeaderboardSortField>(() => {
    const nextField = sorting[0]?.id
    switch (nextField) {
      case "name":
      case "tier":
      case "overall_avg":
      case "total_finishes":
      case "total_playtime":
      case "average_playtime_per_player":
      case "median_first_completion_time":
      case "pro_nub_ratio":
      case "unique_pro_finishes":
      case "unique_nub_finishes":
        return nextField
      default:
        return "unique_nub_finishes"
    }
  }, [sorting])

  const sortDirection: SortDirection =
    sorting[0]?.desc === false ? "asc" : "desc"

  const sortedRows = useMemo(
    () => sortMaps(filteredRows, sortField, sortDirection),
    [filteredRows, sortDirection, sortField],
  )

  const visibleRows = useMemo<MapLeaderboardTableRow[]>(
    () =>
      sortedRows
        .slice(pageIndex * pageSize, (pageIndex + 1) * pageSize)
        .map((row, index) => ({
          ...row,
          rank: pageIndex * pageSize + index + 1,
        })),
    [pageIndex, pageSize, sortedRows],
  )
  const columns = useMemo(() => getMapLeaderboardColumns(t), [t])
  const pageCount = Math.max(1, Math.ceil(filteredRows.length / pageSize))

  useEffect(() => {
    if (pageIndex <= pageCount - 1) {
      return
    }
    setPageIndex(pageCount - 1)
  }, [pageCount, pageIndex])

  const resetFilters = () => {
    startTransition(() => {
      setSelectedTier("all")
      setMinUniqueFinishes("")
      setMaxUniqueFinishes("")
      setMinPlaytime("")
      setMaxPlaytime("")
      setPageIndex(0)
    })
  }

  return (
    <div className="space-y-6">
      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 sm:px-8 sm:pt-8 sm:pb-6">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2 rounded-full border border-border/70 bg-background/70 px-3 py-2 text-sm text-muted-foreground">
                  <Filter className="size-4" />
                  <span>Filters</span>
                </div>
                <TierSelector
                  value={selectedTier}
                  onValueChange={(nextValue) => {
                    startTransition(() => {
                      setSelectedTier(nextValue)
                      setPageIndex(0)
                    })
                  }}
                  triggerClassName="w-auto"
                  ariaLabel="Filter maps leaderboard by tier"
                />
                <Input
                  value={minUniqueFinishes}
                  onChange={(event) => {
                    startTransition(() => {
                      setMinUniqueFinishes(event.target.value)
                      setPageIndex(0)
                    })
                  }}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  placeholder="Min unique"
                  className="w-full sm:w-32"
                  aria-label="Minimum unique finishes"
                />
                <Input
                  value={maxUniqueFinishes}
                  onChange={(event) => {
                    startTransition(() => {
                      setMaxUniqueFinishes(event.target.value)
                      setPageIndex(0)
                    })
                  }}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  placeholder="Max unique"
                  className="w-full sm:w-32"
                  aria-label="Maximum unique finishes"
                />
                <Input
                  value={minPlaytime}
                  onChange={(event) => {
                    startTransition(() => {
                      setMinPlaytime(event.target.value)
                      setPageIndex(0)
                    })
                  }}
                  type="number"
                  inputMode="decimal"
                  min={0}
                  placeholder="Min playtime"
                  className="w-full sm:w-32"
                  aria-label="Minimum total playtime"
                />
                <Input
                  value={maxPlaytime}
                  onChange={(event) => {
                    startTransition(() => {
                      setMaxPlaytime(event.target.value)
                      setPageIndex(0)
                    })
                  }}
                  type="number"
                  inputMode="decimal"
                  min={0}
                  placeholder="Max playtime"
                  className="w-full sm:w-32"
                  aria-label="Maximum total playtime"
                />
              </div>

              <button
                type="button"
                onClick={resetFilters}
                className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                <SearchX className="size-4" />
                Clear filters
              </button>
            </div>

            <div className="text-sm text-muted-foreground">
              Total{" "}
              <span className="font-medium text-foreground">
                {new Intl.NumberFormat("en-US").format(filteredRows.length)}
              </span>{" "}
              Maps
            </div>
          </div>
        </CardContent>
      </Card>

      {mapsQuery.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Unable to load maps leaderboard</AlertTitle>
          <AlertDescription>
            {extractErrorMessage(mapsQuery.error)}
          </AlertDescription>
        </Alert>
      ) : null}

      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
          <DataTable
            columns={columns}
            data={visibleRows}
            isLoading={mapsQuery.isLoading}
            emptyText="No maps matched the current filters."
            stickyHeader
            stickyHeaderTopClassName="top-16"
            tableContainerClassName="md:overflow-visible"
            tableClassName="table-fixed border-separate border-spacing-0"
            showFooter={false}
            serverPagination={{
              pageIndex,
              pageSize,
              totalCount: filteredRows.length,
              onPageChange: setPageIndex,
              onPageSizeChange: (nextPageSize) => {
                setPageSize(nextPageSize)
                setPageIndex(0)
              },
            }}
            sorting={{
              state: sorting,
              onSortingChange,
              manualSorting: true,
            }}
          />
          <TablePaginationFooter
            totalLabel="Maps"
            totalCount={filteredRows.length}
            pageIndex={pageIndex}
            pageCount={pageCount}
            pageSize={pageSize}
            onPageIndexChange={setPageIndex}
            onPageSizeChange={(nextPageSize) => {
              setPageSize(nextPageSize)
              setPageIndex(0)
            }}
          />
        </CardContent>
      </Card>
    </div>
  )
}
