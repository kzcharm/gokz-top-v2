import { useQuery } from "@tanstack/react-query"
import { ArrowLeft, ArrowRight, Search } from "lucide-react"
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
} from "react"

import { type MapPublic, MapsService } from "@/client"
import { MapCard } from "@/components/Maps/MapCard"
import { PendingMaps } from "@/components/Maps/PendingMaps"
import { type AppScope, useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const PAGE_SIZE = 24

const MAP_SORT_OPTIONS = [
  { label: "Name A-Z", value: "name-asc" },
  { label: "Name Z-A", value: "name-desc" },
  { label: "Tier low-high", value: "tier-asc" },
  { label: "Tier high-low", value: "tier-desc" },
  { label: "Updated newest-first", value: "updated-desc" },
  { label: "Updated oldest-first", value: "updated-asc" },
  { label: "Created newest-first", value: "created-desc" },
  { label: "Created oldest-first", value: "created-asc" },
] as const

type MapsSortValue = (typeof MAP_SORT_OPTIONS)[number]["value"]

function getMapTierForScope(map: MapPublic, scope: AppScope) {
  return map.tiers[scope]
}

function sortMaps(maps: MapPublic[], sort: MapsSortValue, scope: AppScope) {
  return [...maps].sort((left, right) => {
    const leftTier = getMapTierForScope(left, scope)
    const rightTier = getMapTierForScope(right, scope)

    switch (sort) {
      case "name-desc":
        return right.name.localeCompare(left.name)
      case "tier-asc":
        return leftTier - rightTier || left.name.localeCompare(right.name)
      case "tier-desc":
        return rightTier - leftTier || left.name.localeCompare(right.name)
      case "updated-desc":
        return (
          Date.parse(right.updated_on) - Date.parse(left.updated_on) ||
          left.name.localeCompare(right.name)
        )
      case "updated-asc":
        return (
          Date.parse(left.updated_on) - Date.parse(right.updated_on) ||
          left.name.localeCompare(right.name)
        )
      case "created-desc":
        return (
          Date.parse(right.created_on) - Date.parse(left.created_on) ||
          left.name.localeCompare(right.name)
        )
      case "created-asc":
        return (
          Date.parse(left.created_on) - Date.parse(right.created_on) ||
          left.name.localeCompare(right.name)
        )
      default:
        return left.name.localeCompare(right.name)
    }
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
  const [sort, setSort] = useState<MapsSortValue>("name-asc")
  const [page, setPage] = useState(1)

  const mapsQuery = useQuery({
    queryKey: ["maps", "catalog"],
    queryFn: () =>
      MapsService.readMaps({ offset: 0, limit: 10000, isValidated: true }),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  useEffect(() => {
    startTransition(() => {
      setPage(1)
    })
  }, [])

  const filteredMaps = useMemo(() => {
    const normalizedQuery = deferredSearch.trim().toLowerCase()
    if (normalizedQuery === "") {
      return mapsQuery.data ?? []
    }

    return (mapsQuery.data ?? []).filter((map) =>
      map.name.toLowerCase().includes(normalizedQuery),
    )
  }, [deferredSearch, mapsQuery.data])

  const sortedMaps = useMemo(
    () => sortMaps(filteredMaps, sort, scope),
    [filteredMaps, scope, sort],
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

  return (
    <div className="space-y-8">
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
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative block w-full lg:max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchInput}
              onChange={(event) => {
                const nextValue = event.target.value
                startTransition(() => {
                  setSearchInput(nextValue)
                })
              }}
              placeholder="Search maps by name"
              aria-label="Search maps by name"
              className="pl-9"
            />
          </div>

          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
            <Select
              value={sort}
              onValueChange={(value) => {
                startTransition(() => {
                  setSort(value as MapsSortValue)
                })
              }}
            >
              <SelectTrigger className="w-full sm:w-64" aria-label="Sort maps">
                <SelectValue placeholder="Sort maps" />
              </SelectTrigger>
              <SelectContent>
                {MAP_SORT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
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
