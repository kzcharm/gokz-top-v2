import { useQuery } from "@tanstack/react-query"
import { Search, ShieldAlert, X } from "lucide-react"
import { useDeferredValue, useEffect, useRef, useState } from "react"

import { OpenAPI } from "@/client/core/OpenAPI"
import { DataTable } from "@/components/Common/DataTable"
import {
  getPlayerDisplayName,
  PlayerDisplay,
} from "@/components/Common/PlayerDisplay"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { type GraphqlPlayer, searchPlayersGraphql } from "@/lib/player-graphql"
import { cn } from "@/lib/utils"
import { extractErrorMessage } from "@/utils"

import { type BanRow, banColumns } from "./columns"

type BansResponse = {
  count: number
  data: BanRow[]
}

const DEFAULT_PAGE_SIZE = 20

async function fetchBans({
  pageIndex,
  pageSize,
  steamid64,
}: {
  pageIndex: number
  pageSize: number
  steamid64?: string | null
}) {
  const params = new URLSearchParams({
    offset: `${pageIndex * pageSize}`,
    limit: `${pageSize}`,
  })
  if (steamid64) {
    params.set("steamid64", steamid64)
  }
  const response = await fetch(`${OpenAPI.BASE}/v1/bans?${params.toString()}`)
  if (!response.ok) {
    throw new Error("Failed to load bans")
  }

  return (await response.json()) as BansResponse
}

export function BansPage() {
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [expandedBanId, setExpandedBanId] = useState<string | null>(null)
  const [searchInput, setSearchInput] = useState("")
  const [selectedPlayer, setSelectedPlayer] = useState<GraphqlPlayer | null>(
    null,
  )
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const searchBlurTimeoutRef = useRef<number | null>(null)
  const deferredSearchInput = useDeferredValue(searchInput)
  const playerSearchQuery = deferredSearchInput.trim()

  const playerSearchQueryResult = useQuery({
    queryKey: ["graphql", "players", "search", playerSearchQuery],
    enabled: playerSearchQuery.length > 0,
    queryFn: async () =>
      (await searchPlayersGraphql(playerSearchQuery, 8)).data,
    staleTime: 30_000,
  })

  const bansQuery = useQuery({
    queryKey: ["bans", pageIndex, pageSize, selectedPlayer?.steamid64 ?? null],
    queryFn: () =>
      fetchBans({
        pageIndex,
        pageSize,
        steamid64: selectedPlayer?.steamid64 ?? null,
      }),
    staleTime: 30_000,
  })

  useEffect(() => {
    setExpandedBanId(null)
  }, [])

  useEffect(() => {
    return () => {
      if (searchBlurTimeoutRef.current !== null) {
        window.clearTimeout(searchBlurTimeoutRef.current)
      }
    }
  }, [])

  if (bansQuery.isError) {
    return (
      <Alert variant="destructive">
        <ShieldAlert />
        <AlertTitle>Unable to load bans</AlertTitle>
        <AlertDescription className="gap-3">
          <p>{extractErrorMessage(bansQuery.error)}</p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void bansQuery.refetch()
            }}
          >
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    )
  }

  const bans = bansQuery.data?.data ?? []
  const totalCount = bansQuery.data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize))
  const searchResults: GraphqlPlayer[] = playerSearchQueryResult.data ?? []
  const showSearchResults =
    isSearchFocused && selectedPlayer === null && playerSearchQuery.length > 0

  const handleSelectPlayer = (player: GraphqlPlayer) => {
    setSelectedPlayer(player)
    setSearchInput(getPlayerDisplayName(player))
    setIsSearchFocused(false)
    setPageIndex(0)
  }

  const clearSelectedPlayer = () => {
    setSelectedPlayer(null)
    setSearchInput("")
    setIsSearchFocused(false)
    setPageIndex(0)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Bans</h1>
      </div>

      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 sm:px-8 sm:pt-8 sm:pb-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
            <div className="w-full lg:max-w-[18rem]">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  aria-label="Search players"
                  value={searchInput}
                  onChange={(event) => {
                    if (searchBlurTimeoutRef.current !== null) {
                      window.clearTimeout(searchBlurTimeoutRef.current)
                    }
                    setSearchInput(event.target.value)
                    setIsSearchFocused(true)
                    if (selectedPlayer !== null) {
                      setSelectedPlayer(null)
                      setPageIndex(0)
                    }
                  }}
                  onFocus={() => {
                    if (searchBlurTimeoutRef.current !== null) {
                      window.clearTimeout(searchBlurTimeoutRef.current)
                    }
                    setIsSearchFocused(true)
                  }}
                  onBlur={() => {
                    searchBlurTimeoutRef.current = window.setTimeout(() => {
                      setIsSearchFocused(false)
                    }, 100)
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && searchResults.length > 0) {
                      event.preventDefault()
                      handleSelectPlayer(searchResults[0])
                    }
                    if (event.key === "Escape") {
                      setIsSearchFocused(false)
                    }
                  }}
                  placeholder="Search player ..."
                  className="pr-10 pl-9"
                />
                {selectedPlayer ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="absolute top-1/2 right-1 -translate-y-1/2"
                    onClick={clearSelectedPlayer}
                    aria-label="Clear player filter"
                  >
                    <X className="size-4" />
                  </Button>
                ) : null}
                {showSearchResults ? (
                  <div className="absolute top-[calc(100%+0.5rem)] right-0 left-0 z-20 overflow-hidden rounded-xl border border-border/70 bg-card shadow-lg">
                    {playerSearchQueryResult.isLoading ? (
                      <div className="px-4 py-3 text-sm text-muted-foreground">
                        Searching players...
                      </div>
                    ) : playerSearchQueryResult.isError ? (
                      <div className="px-4 py-3 text-sm text-destructive">
                        Unable to search players right now.
                      </div>
                    ) : searchResults.length === 0 ? (
                      <div className="px-4 py-3 text-sm text-muted-foreground">
                        No players found.
                      </div>
                    ) : (
                      <div className="py-1">
                        {searchResults.map((player) => (
                          <button
                            key={player.steamid64}
                            type="button"
                            className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm transition-colors hover:bg-muted/60"
                            onMouseDown={(event) => {
                              event.preventDefault()
                              handleSelectPlayer(player)
                            }}
                          >
                            <PlayerDisplay
                              player={player}
                              disableProfileLink
                              className="min-w-0"
                            />
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="gap-0 overflow-hidden rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-b-none">
          <DataTable
            columns={banColumns}
            data={bans}
            isLoading={bansQuery.isLoading}
            emptyText="No bans found."
            showFooter={false}
            getRowId={(row) => `${row.id}`}
            expandedRowId={expandedBanId}
            getRowProps={(row) => {
              const isExpanded = expandedBanId === `${row.id}`
              return {
                className: cn(
                  "cursor-pointer",
                  isExpanded && "bg-muted/25 hover:bg-muted/25",
                ),
                onClick: () => {
                  setExpandedBanId((currentId) =>
                    currentId === `${row.id}` ? null : `${row.id}`,
                  )
                },
              }
            }}
            renderExpandedContent={(row) => (
              <div className="rounded-lg border bg-background/70 p-3">
                <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-6 text-foreground">
                  {row.stats?.trim() || "No detail stats available."}
                </pre>
              </div>
            )}
            serverPagination={{
              pageIndex,
              pageSize,
              totalCount,
              onPageChange: setPageIndex,
              onPageSizeChange: (nextPageSize) => {
                setPageSize(nextPageSize)
                setPageIndex(0)
              },
            }}
          />
          <TablePaginationFooter
            totalLabel="Bans"
            totalCount={totalCount}
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
