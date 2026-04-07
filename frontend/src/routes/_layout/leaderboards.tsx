import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import {
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { LocateFixed, Search } from "lucide-react"
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

import { LeaderboardsService, type PlayerPublic } from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { DataTable } from "@/components/Common/DataTable"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { columns } from "@/components/Leaderboards/columns"
import { useScope } from "@/components/scope-provider"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import useAuth from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"
import { cn } from "@/lib/utils"
import { extractErrorMessage } from "@/utils"

export const Route = createFileRoute("/_layout/leaderboards")({
  component: LeaderboardsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Leaderboards"),
      },
    ],
  }),
})

function LeaderboardsRoute() {
  const { scope } = useScope()
  const { user: currentUser } = useAuth()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [searchInput, setSearchInput] = useState("")
  const [isLocatingPlayer, setIsLocatingPlayer] = useState(false)
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const [pendingSpotlightSteamid64, setPendingSpotlightSteamid64] = useState<
    string | null
  >(null)
  const [sorting, setSorting] = useState<SortingState>([
    { id: "rating", desc: true },
  ])
  const deferredSearchInput = useDeferredValue(searchInput)
  const spotlightTimeoutRef = useRef<number | null>(null)
  const spotlightStartTimeoutRef = useRef<number | null>(null)
  const searchBlurTimeoutRef = useRef<number | null>(null)
  const playerSearchQuery = deferredSearchInput.trim()

  const sortBy =
    sorting[0]?.id === "rating_easy" ||
    sorting[0]?.id === "rating_hard" ||
    sorting[0]?.id === "points" ||
    sorting[0]?.id === "wrs_nub" ||
    sorting[0]?.id === "wrs_pro" ||
    sorting[0]?.id === "records_900_plus" ||
    sorting[0]?.id === "records_800_plus" ||
    sorting[0]?.id === "unique_map_finishes"
      ? sorting[0].id
      : "rating"

  const leaderboardQuery = useQuery({
    queryKey: ["leaderboards", "players", scope, pageIndex, pageSize, sortBy],
    queryFn: () =>
      LeaderboardsService.readPlayerLeaderboard({
        scope,
        offset: pageIndex * pageSize,
        limit: pageSize,
        sortBy,
        sortOrder: "desc",
      }),
  })
  const playerSearchQueryResult = useQuery({
    queryKey: ["players", "search", playerSearchQuery],
    enabled: playerSearchQuery.length > 0,
    queryFn: async () => {
      const response = await fetch(
        `${OpenAPI.BASE}/v1/players/search?q=${encodeURIComponent(playerSearchQuery)}&limit=10`,
      )
      if (!response.ok) {
        throw new Error("Failed to search players")
      }

      const data = (await response.json()) as {
        data?: PlayerPublic[]
      }
      return data.data ?? []
    },
  })

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    const nextSort = [
      {
        id: next[0]?.id ?? sorting[0]?.id ?? "rating",
        desc: true,
      },
    ]
    setSorting(nextSort)
    setPageIndex(0)
  }

  const tableData = useMemo(
    () => leaderboardQuery.data?.data ?? [],
    [leaderboardQuery.data],
  )

  useEffect(() => {
    return () => {
      if (spotlightStartTimeoutRef.current !== null) {
        window.clearTimeout(spotlightStartTimeoutRef.current)
      }
      if (spotlightTimeoutRef.current !== null) {
        window.clearTimeout(spotlightTimeoutRef.current)
      }
      if (searchBlurTimeoutRef.current !== null) {
        window.clearTimeout(searchBlurTimeoutRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (!leaderboardQuery.isError || !leaderboardQuery.error) {
      return
    }

    toast.error("Unable to load leaderboard", {
      description: extractErrorMessage(leaderboardQuery.error),
      id: `leaderboards-load-error-${leaderboardQuery.errorUpdatedAt}`,
    })
  }, [
    leaderboardQuery.error,
    leaderboardQuery.errorUpdatedAt,
    leaderboardQuery.isError,
  ])

  useEffect(() => {
    if (!pendingSpotlightSteamid64) {
      return
    }

    const hasTargetRow = tableData.some(
      (row) => row.player.steamid64 === pendingSpotlightSteamid64,
    )
    if (!hasTargetRow) {
      return
    }

    const row = document.querySelector<HTMLTableRowElement>(
      `[data-player-steamid64="${pendingSpotlightSteamid64}"]`,
    )
    if (!row) {
      return
    }

    row.scrollIntoView({
      behavior: "smooth",
      block: "center",
      inline: "nearest",
    })

    if (spotlightStartTimeoutRef.current !== null) {
      window.clearTimeout(spotlightStartTimeoutRef.current)
    }
    if (spotlightTimeoutRef.current !== null) {
      window.clearTimeout(spotlightTimeoutRef.current)
    }

    spotlightStartTimeoutRef.current = window.setTimeout(() => {
      row.classList.remove("leaderboard-self-spotlight")
      void row.getBoundingClientRect()
      row.classList.add("leaderboard-self-spotlight")

      spotlightTimeoutRef.current = window.setTimeout(() => {
        row.classList.remove("leaderboard-self-spotlight")
        spotlightTimeoutRef.current = null
      }, 1800)

      spotlightStartTimeoutRef.current = null
    }, 450)

    setPendingSpotlightSteamid64(null)
  }, [pendingSpotlightSteamid64, tableData])

  const locatePlayer = async ({
    identifier,
    spotlightSteamid64,
    onNotRanked,
  }: {
    identifier: string
    spotlightSteamid64: string
    onNotRanked: () => void
  }) => {
    setIsLocatingPlayer(true)
    try {
      const token = localStorage.getItem("access_token")
      const response = await fetch(
        `${OpenAPI.BASE}/v1/leaderboards/players/${encodeURIComponent(identifier)}?scope=${scope}`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        },
      )

      if (!response.ok) {
        throw new Error("Failed to fetch leaderboard rank")
      }

      const data = (await response.json()) as { rank?: number | null }
      if (!data.rank) {
        onNotRanked()
        return
      }

      setSorting([{ id: "rating", desc: true }])
      setPendingSpotlightSteamid64(spotlightSteamid64)
      setPageIndex(Math.floor((data.rank - 1) / pageSize))
    } catch {
      toast.error("Could not locate player on the leaderboard", {
        description: "Try again in a moment.",
      })
    } finally {
      setIsLocatingPlayer(false)
    }
  }

  const handleFindMe = async () => {
    if (!currentUser?.steamid64) {
      return
    }

    setSearchInput("")
    setIsSearchFocused(false)
    await locatePlayer({
      identifier: currentUser.steamid64,
      spotlightSteamid64: currentUser.steamid64,
      onNotRanked: () => {
        toast.error("You are not ranked yet", {
          description: "Complete more runs in this scope before using Find Me.",
        })
      },
    })
  }

  const handleSelectPlayer = async (player: PlayerPublic) => {
    setSearchInput(player.name)
    setIsSearchFocused(false)
    await locatePlayer({
      identifier: player.custom_id ?? player.steamid64,
      spotlightSteamid64: player.steamid64,
      onNotRanked: () => {
        toast.error("Player is not ranked yet", {
          description: "Select another player or scope.",
        })
      },
    })
  }

  const searchResults = playerSearchQueryResult.data ?? []
  const showSearchResults = isSearchFocused && playerSearchQuery.length > 0

  return (
    <div className="space-y-6">
      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="space-y-3 p-6 sm:p-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex w-full flex-col gap-3 lg:max-w-[18rem]">
              <h1 className="text-3xl font-semibold tracking-tight">
                Leaderboards
              </h1>
              <div className="relative w-full">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  aria-label="Search players"
                  value={searchInput}
                  onChange={(event) => {
                    if (searchBlurTimeoutRef.current !== null) {
                      window.clearTimeout(searchBlurTimeoutRef.current)
                    }
                    setSearchInput(event.target.value)
                    setIsSearchFocused(true)
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
                      void handleSelectPlayer(searchResults[0])
                    }
                  }}
                  placeholder="Search player ..."
                  className="pl-9"
                />
                {showSearchResults ? (
                  <div className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-20 overflow-hidden rounded-xl border border-border/70 bg-card shadow-lg">
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
                              void handleSelectPlayer(player)
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
            <LoadingButton
              type="button"
              variant="outline"
              loading={isLocatingPlayer}
              disabled={!currentUser?.steamid64}
              onClick={() => void handleFindMe()}
            >
              <LocateFixed />
              Find Me
            </LoadingButton>
          </div>
        </CardContent>
      </Card>

      <Card className="gap-0 overflow-hidden rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0">
          <DataTable
            columns={columns}
            data={tableData}
            isLoading={leaderboardQuery.isLoading}
            getRowProps={(row) => ({
              "data-player-steamid64": row.player.steamid64,
              className:
                row.player.steamid64 === currentUser?.steamid64
                  ? cn(
                      "bg-primary/10 ring-1 ring-inset ring-primary/35",
                      "transition-[background-color,box-shadow,transform] duration-500",
                      "hover:bg-primary/15",
                    )
                  : undefined,
            })}
            serverPagination={{
              pageIndex,
              pageSize,
              totalCount: leaderboardQuery.data?.count ?? 0,
              onPageChange: setPageIndex,
              onPageSizeChange: (size) => {
                setPageSize(size)
                setPageIndex(0)
              },
            }}
            sorting={{
              state: sorting,
              onSortingChange,
              manualSorting: true,
            }}
          />
        </CardContent>
      </Card>
    </div>
  )
}
