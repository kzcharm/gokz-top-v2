import { useQuery } from "@tanstack/react-query"
import {
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { LocateFixed, Search, Users } from "lucide-react"
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { LeaderboardsService } from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import type { PlayerLeaderboardsPublic } from "@/client/types.gen"
import { CountryPicker } from "@/components/Common/CountryPicker"
import { DataTable } from "@/components/Common/DataTable"
import {
  getPlayerDisplayName,
  PlayerDisplay,
  type PlayerDisplayPlayer,
} from "@/components/Common/PlayerDisplay"
import { RegionBadge } from "@/components/Common/RegionFlag"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import {
  getLeaderboardColumns,
  type LeaderboardTableRow,
} from "@/components/Leaderboards/columns"
import { useScope } from "@/components/scope-provider"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import useAuth from "@/hooks/useAuth"
import {
  fetchPlayersForDisplay,
  type GraphqlPlayer,
  searchPlayersGraphql,
} from "@/lib/player-graphql"
import { getRegionsQueryOptions } from "@/lib/regions"
import { cn } from "@/lib/utils"
import { extractErrorMessage } from "@/utils"

const LEADERBOARDS_PAGE_SIZE_STORAGE_KEY = "gokz-leaderboards-page-size"
const LEADERBOARDS_PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const

type LeaderboardFetchParams = {
  scope: string
  offset: number
  limit: number
  sortBy: string
  sortOrder: "desc"
  country?: string
  region?: string
  friendsOnly?: boolean
  includeCount: boolean
}

async function fetchLeaderboardPage(
  params: LeaderboardFetchParams,
): Promise<PlayerLeaderboardsPublic> {
  const accessToken =
    typeof window === "undefined"
      ? null
      : window.localStorage.getItem("access_token")
  const searchParams = new URLSearchParams({
    scope: params.scope,
    offset: `${params.offset}`,
    limit: `${params.limit}`,
    sort_by: params.sortBy,
    sort_order: params.sortOrder,
    include_count: params.includeCount ? "true" : "false",
  })

  if (params.country) {
    searchParams.set("country", params.country)
  }
  if (params.region) {
    searchParams.set("region", params.region)
  }
  if (params.friendsOnly) {
    searchParams.set("friends_only", "true")
  }

  const response = await fetch(
    `${OpenAPI.BASE}/v1/leaderboards/players?${searchParams.toString()}`,
    {
      credentials: "include",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    },
  )

  if (!response.ok) {
    let message = `Failed to fetch leaderboard (${response.status})`

    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) {
        message = payload.detail
      }
    } catch {
      // Keep the fallback message when the error payload is not JSON.
    }

    throw new Error(message)
  }

  return (await response.json()) as PlayerLeaderboardsPublic
}

export function PlayersLeaderboardTab() {
  const { t } = useTranslation()
  const { scope } = useScope()
  const { user: currentUser } = useAuth()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(() => {
    if (typeof window === "undefined") {
      return 20
    }

    const storedPageSize = Number(
      window.localStorage.getItem(LEADERBOARDS_PAGE_SIZE_STORAGE_KEY),
    )

    return LEADERBOARDS_PAGE_SIZE_OPTIONS.includes(
      storedPageSize as (typeof LEADERBOARDS_PAGE_SIZE_OPTIONS)[number],
    )
      ? storedPageSize
      : 20
  })
  const [searchInput, setSearchInput] = useState("")
  const [isLocatingPlayer, setIsLocatingPlayer] = useState(false)
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const [highlightedSteamid64, setHighlightedSteamid64] = useState<
    string | null
  >(null)
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
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null)
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [isFriendsOnly, setIsFriendsOnly] = useState(false)

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
    queryKey: [
      "leaderboards",
      "players",
      "page",
      scope,
      pageIndex,
      pageSize,
      sortBy,
      selectedCountry,
      selectedRegion,
      isFriendsOnly,
    ],
    queryFn: () =>
      fetchLeaderboardPage({
        scope,
        offset: pageIndex * pageSize,
        limit: pageSize + 1,
        sortBy,
        sortOrder: "desc",
        country: selectedCountry ?? undefined,
        region: selectedRegion ?? undefined,
        friendsOnly: isFriendsOnly,
        includeCount: false,
      }),
    staleTime: 30_000,
  })
  const leaderboardCountQuery = useQuery({
    queryKey: [
      "leaderboards",
      "players",
      "count",
      scope,
      sortBy,
      selectedCountry,
      selectedRegion,
      isFriendsOnly,
    ],
    queryFn: () =>
      LeaderboardsService.readPlayerLeaderboard({
        scope,
        offset: 0,
        limit: 1,
        sortBy,
        sortOrder: "desc",
        country: selectedCountry ?? undefined,
        region: selectedRegion ?? undefined,
        friendsOnly: isFriendsOnly,
      }),
    staleTime: 30_000,
  })
  const leaderboardEntries = useMemo(
    () => leaderboardQuery.data?.data ?? [],
    [leaderboardQuery.data],
  )
  const hasNextPage = leaderboardEntries.length > pageSize
  const visibleLeaderboardEntries = useMemo(
    () => leaderboardEntries.slice(0, pageSize),
    [leaderboardEntries, pageSize],
  )
  const leaderboardPlayerSteamid64s = useMemo(
    () => visibleLeaderboardEntries.map((entry) => entry.player.steamid64),
    [visibleLeaderboardEntries],
  )
  const leaderboardPlayersQuery = useQuery({
    queryKey: [
      "graphql",
      "players",
      "leaderboard",
      scope,
      leaderboardPlayerSteamid64s,
    ],
    enabled: leaderboardPlayerSteamid64s.length > 0,
    queryFn: () => fetchPlayersForDisplay(leaderboardPlayerSteamid64s, scope),
    staleTime: 30_000,
  })
  const regionsQuery = useQuery(getRegionsQueryOptions())
  const playerSearchQueryResult = useQuery({
    queryKey: ["graphql", "players", "search", playerSearchQuery],
    enabled: playerSearchQuery.length > 0,
    queryFn: async () =>
      (await searchPlayersGraphql(playerSearchQuery, 10)).data,
    staleTime: 30_000,
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

  const leaderboardPlayersBySteamid64 = useMemo(() => {
    const playersBySteamid64 = new Map<string, PlayerDisplayPlayer>()
    for (const player of leaderboardPlayersQuery.data ?? []) {
      if (!player) {
        continue
      }
      playersBySteamid64.set(player.steamid64, player)
    }
    return playersBySteamid64
  }, [leaderboardPlayersQuery.data])

  const tableData = useMemo<LeaderboardTableRow[]>(
    () =>
      visibleLeaderboardEntries.map((entry) => {
        const hydratedPlayer = leaderboardPlayersBySteamid64.get(
          entry.player.steamid64,
        )
        return {
          ...entry,
          playerData: hydratedPlayer ?? {
            steamid64: entry.player.steamid64,
            displayName: entry.player.display_name,
            name: entry.player.display_name,
          },
        }
      }),
    [leaderboardPlayersBySteamid64, visibleLeaderboardEntries],
  )
  const columns = useMemo(
    () => getLeaderboardColumns(t, scope, isFriendsOnly),
    [isFriendsOnly, scope, t],
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
    window.localStorage.setItem(
      LEADERBOARDS_PAGE_SIZE_STORAGE_KEY,
      `${pageSize}`,
    )
  }, [pageSize])

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
      const params = new URLSearchParams({ scope })
      if (selectedCountry) {
        params.set("country", selectedCountry)
      }
      if (selectedRegion) {
        params.set("region", selectedRegion)
      }
      if (isFriendsOnly) {
        params.set("friends_only", "true")
      }
      const response = await fetch(
        `${OpenAPI.BASE}/v1/leaderboards/players/${encodeURIComponent(identifier)}?${params.toString()}`,
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
      setHighlightedSteamid64(spotlightSteamid64)
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

  const handleSelectPlayer = async (player: GraphqlPlayer) => {
    setSearchInput(getPlayerDisplayName(player))
    setIsSearchFocused(false)
    await locatePlayer({
      identifier: player.customId ?? player.steamid64,
      spotlightSteamid64: player.steamid64,
      onNotRanked: () => {
        toast.error("Player is not ranked yet", {
          description: "Select another player or scope.",
        })
      },
    })
  }

  const searchResults: GraphqlPlayer[] = playerSearchQueryResult.data ?? []
  const showSearchResults = isSearchFocused && playerSearchQuery.length > 0
  const hasExactCount =
    typeof leaderboardCountQuery.data?.count === "number" &&
    leaderboardCountQuery.data.count >= 0
  const totalPlayers = hasExactCount
    ? leaderboardCountQuery.data!.count
    : pageIndex * pageSize + tableData.length + (hasNextPage ? 1 : 0)
  const pageCount = Math.max(1, Math.ceil(totalPlayers / pageSize))
  const selectedRegionOption =
    regionsQuery.data?.find((region) => region.code === selectedRegion) ?? null

  return (
    <>
      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 sm:px-8 sm:pt-8 sm:pb-6">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex w-full flex-col gap-3 lg:max-w-[22rem]">
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
                    <div className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-30 overflow-hidden rounded-xl border border-border/70 bg-card shadow-lg">
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

              <div className="flex flex-col gap-3 sm:flex-row lg:flex-wrap lg:items-center lg:justify-end">
                <Select
                  disabled={isFriendsOnly}
                  value={selectedRegion ?? "all"}
                  onValueChange={(value) => {
                    const nextRegion = value === "all" ? null : value
                    setSelectedRegion(nextRegion)
                    if (nextRegion !== null) {
                      setSelectedCountry(null)
                    }
                    setPageIndex(0)
                  }}
                >
                  <SelectTrigger className="w-full sm:w-[144px]">
                    {selectedRegionOption ? (
                      <RegionBadge
                        regionCode={selectedRegionOption.code}
                        regionName={selectedRegionOption.name}
                      />
                    ) : (
                      <span className="text-muted-foreground">region</span>
                    )}
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">region</SelectItem>
                    {(regionsQuery.data ?? []).map((region) => (
                      <SelectItem key={region.code} value={region.code}>
                        <RegionBadge
                          regionCode={region.code}
                          regionName={region.name}
                        />
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <div className="w-full sm:w-[176px]">
                  <CountryPicker
                    value={selectedCountry}
                    disabled={isFriendsOnly}
                    onChange={(value) => {
                      setSelectedCountry(value)
                      if (value !== null) {
                        setSelectedRegion(null)
                      }
                      setPageIndex(0)
                    }}
                    placeholder="country"
                    clearLabel="country"
                  />
                </div>

                <Button
                  type="button"
                  variant="outline"
                  aria-pressed={isFriendsOnly}
                  className={cn(
                    "border-border/70 bg-background/80",
                    isFriendsOnly &&
                      "border-amber-500/50 bg-amber-500/12 text-amber-950 hover:bg-amber-500/18 dark:text-amber-100",
                  )}
                  onClick={() => {
                    if (!currentUser?.steamid64) {
                      toast.warning(
                        t("leaderboards.players.friends.loginRequiredTitle"),
                        {
                          description: t(
                            "leaderboards.players.friends.loginRequiredDescription",
                          ),
                        },
                      )
                      return
                    }

                    const nextValue = !isFriendsOnly
                    setIsFriendsOnly(nextValue)
                    if (nextValue) {
                      setSelectedCountry(null)
                      setSelectedRegion(null)
                    }
                    setPageIndex(0)
                  }}
                >
                  <Users />
                  {t("leaderboards.players.friends.label")}
                </Button>

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
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
          <DataTable
            columns={columns}
            data={tableData}
            isLoading={leaderboardQuery.isLoading}
            stickyHeader
            stickyHeaderTopClassName="top-16"
            tableContainerClassName="md:overflow-visible"
            tableClassName="border-separate border-spacing-0"
            showFooter={false}
            getRowProps={(row) => ({
              "data-player-steamid64": row.player.steamid64,
              className:
                row.player.steamid64 === currentUser?.steamid64 ||
                row.player.steamid64 === highlightedSteamid64
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
          <TablePaginationFooter
            totalLabel="Players"
            totalCount={totalPlayers}
            pageIndex={pageIndex}
            pageCount={pageCount}
            pageSize={pageSize}
            onPageIndexChange={setPageIndex}
            onPageSizeChange={(size) => {
              setPageSize(size)
              setPageIndex(0)
            }}
            hasNextPage={hasNextPage}
            hasExactCount={hasExactCount}
          />
        </CardContent>
      </Card>
    </>
  )
}
