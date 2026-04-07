import { useQuery } from "@tanstack/react-query"
import { Search, ShieldAlert, X } from "lucide-react"
import { useDeferredValue, useEffect, useRef, useState } from "react"

import { type PlayerPublic } from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { DataTable } from "@/components/Common/DataTable"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
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
  const [selectedPlayer, setSelectedPlayer] = useState<PlayerPublic | null>(null)
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const searchBlurTimeoutRef = useRef<number | null>(null)
  const deferredSearchInput = useDeferredValue(searchInput)
  const playerSearchQuery = deferredSearchInput.trim()

  const playerSearchQueryResult = useQuery({
    queryKey: ["players", "search", playerSearchQuery],
    enabled: playerSearchQuery.length > 0,
    queryFn: async () => {
      const response = await fetch(
        `${OpenAPI.BASE}/v1/players/search?q=${encodeURIComponent(playerSearchQuery)}&limit=8`,
      )
      if (!response.ok) {
        throw new Error("Failed to search players")
      }

      const data = (await response.json()) as {
        data?: PlayerPublic[]
      }
      return data.data ?? []
    },
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
  }, [pageIndex, pageSize, bansQuery.dataUpdatedAt])

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
  const searchResults = playerSearchQueryResult.data ?? []
  const showSearchResults =
    isSearchFocused &&
    selectedPlayer === null &&
    playerSearchQuery.length > 0

  const handleSelectPlayer = (player: PlayerPublic) => {
    setSelectedPlayer(player)
    setSearchInput(player.alias || player.name)
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
      <Card>
        <CardHeader className="gap-3">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3">
              <div className="rounded-xl border border-red-300/60 bg-red-100/70 p-2 text-red-700 shadow-sm dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">
                <ShieldAlert className="size-5" />
              </div>
              <CardTitle className="text-xl">Bans</CardTitle>
            </div>
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
        </CardHeader>
        <CardContent>
          <DataTable
            columns={banColumns}
            data={bans}
            isLoading={bansQuery.isLoading}
            emptyText="No bans found."
            pageInputEnabled
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
            footerSummary={
              <>
                Total{" "}
                <span className="font-medium text-foreground">
                  {totalCount}
                </span>{" "}
                bans
              </>
            }
          />
        </CardContent>
      </Card>
    </div>
  )
}
