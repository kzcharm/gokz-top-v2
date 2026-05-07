import { useMutation, useQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import {
  type ColumnDef,
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { ArrowDown, ArrowUp, Search, Users, X } from "lucide-react"
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react"

import {
  type AdminPlayerSessionIpLinksPublic,
  type AdminPlayerSessionPublic,
  AdminPlayerSessionsService,
  type PlayerPublic,
  PlayersService,
  UsersService,
} from "@/client"
import {
  AdminControlsCard,
  AdminPageHeader,
  AdminTableCard,
} from "@/components/Admin/AdminPageLayout"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { formatTimerTime } from "@/components/Servers/utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"
import { isSuperuser } from "@/lib/user-roles"

type SessionSortBy = "connected_at" | "disconnect_at" | "duration_seconds"
type AltMatchMode = "exact_ip" | "same_24" | "same_16_city"

export const Route = createFileRoute("/_layout/admin/player-sessions")({
  component: AdminPlayerSessions,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
    const user = await UsersService.readUserMe().catch(() => {
      localStorage.removeItem("access_token")
      throw redirect({
        to: "/login",
      })
    })
    if (!isSuperuser(user)) {
      throw redirect({
        to: "/",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: getPageTitle("Admin Player Sessions"),
      },
    ],
  }),
})

function AdminPlayerSessions() {
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [latestOnly, setLatestOnly] = useState(false)
  const [revealedSessionIds, setRevealedSessionIds] = useState<Set<string>>(
    () => new Set(),
  )
  const [sorting, setSorting] = useState<SortingState>([
    { id: "connected_at", desc: true },
  ])
  const activeSort = sorting[0] ?? { id: "connected_at", desc: true }
  const sortBy = toSessionSortBy(activeSort.id)
  const sortOrder = activeSort.desc ? "desc" : "asc"

  const query = useQuery({
    queryKey: [
      "admin-player-sessions",
      pageIndex,
      pageSize,
      latestOnly,
      sortBy,
      sortOrder,
    ],
    queryFn: () =>
      AdminPlayerSessionsService.readAdminPlayerSessions({
        offset: pageIndex * pageSize,
        limit: pageSize,
        latestOnly,
        sortBy,
        sortOrder,
      }),
  })

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    const nextSort =
      next.length > 0 ? [next[0]] : [{ id: "connected_at", desc: true }]
    setSorting(nextSort)
    setPageIndex(0)
  }

  const columns = useMemo<ColumnDef<AdminPlayerSessionPublic>[]>(
    () => [
      {
        accessorKey: "player",
        header: "Player",
        cell: ({ row }) => <PlayerDisplay player={row.original.player} />,
      },
      {
        accessorKey: "server_group_name",
        header: "Server",
        cell: ({ row }) => (
          <div className="max-w-56 truncate font-medium">
            {row.original.server_group_name}
          </div>
        ),
      },
      {
        accessorKey: "map_name",
        header: "Map",
        cell: ({ row }) => (
          <MapDisplay mapName={row.original.map_name} className="w-48" />
        ),
      },
      {
        accessorKey: "connected_at",
        header: ({ column }) => (
          <SortableHeader column={column} label="Connected" />
        ),
        cell: ({ row }) => (
          <FormattedDateTime value={row.original.connected_at} />
        ),
      },
      {
        accessorKey: "disconnect_at",
        header: ({ column }) => (
          <SortableHeader column={column} label="Disconnected" />
        ),
        cell: ({ row }) => (
          <FormattedDateTime
            value={row.original.disconnect_at}
            fallback="Open"
          />
        ),
      },
      {
        accessorKey: "duration_seconds",
        header: ({ column }) => (
          <div className="flex justify-end">
            <SortableHeader column={column} label="Duration" />
          </div>
        ),
        cell: ({ row }) => (
          <div className="text-right font-mono text-sm">
            {formatTimerTime(row.original.duration_seconds ?? null)}
          </div>
        ),
      },
      {
        accessorKey: "ip_address",
        header: "IP",
        cell: ({ row }) => {
          const isRevealed = revealedSessionIds.has(row.original.id)
          return (
            <div className="min-w-32">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-auto px-1 py-0 font-mono text-sm"
                aria-label={`${isRevealed ? "Hide" : "Reveal"} IP for session ${row.original.id}`}
                onClick={() => {
                  setRevealedSessionIds((current) => {
                    const next = new Set(current)
                    if (next.has(row.original.id)) {
                      next.delete(row.original.id)
                    } else {
                      next.add(row.original.id)
                    }
                    return next
                  })
                }}
              >
                {isRevealed ? row.original.ip_address : "***.***.***.***"}
              </Button>
            </div>
          )
        },
      },
    ],
    [revealedSessionIds],
  )

  const totalCount = query.data?.count ?? 0

  return (
    <div className="flex flex-col gap-6">
      <AdminPageHeader title="Player Sessions" />
      <AdminControlsCard>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <FindAltsDialog />
          <div className="flex items-center gap-3">
            <Switch
              id="latest-session-per-player"
              aria-label="Latest session per player"
              checked={latestOnly}
              onCheckedChange={(checked) => {
                setLatestOnly(checked)
                setPageIndex(0)
              }}
            />
            <label
              htmlFor="latest-session-per-player"
              className="text-sm font-medium"
            >
              Latest session per player
            </label>
          </div>
        </div>
      </AdminControlsCard>
      <AdminTableCard>
        <DataTable
          columns={columns}
          data={query.data?.data ?? []}
          isLoading={query.isLoading}
          stickyHeader
          stickyHeaderTopClassName="top-16"
          tableContainerClassName="md:overflow-visible"
          tableClassName="border-separate border-spacing-0"
          showFooter={false}
          emptyText="No player sessions found."
          serverPagination={{
            pageIndex,
            pageSize,
            totalCount,
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
          totalLabel="Sessions"
          totalCount={totalCount}
          pageIndex={pageIndex}
          pageCount={Math.max(1, Math.ceil(totalCount / pageSize))}
          pageSize={pageSize}
          onPageIndexChange={setPageIndex}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPageIndex(0)
          }}
          hasExactCount={!query.isLoading}
          isTotalCountLoading={query.isLoading}
        />
      </AdminTableCard>
    </div>
  )
}

function FindAltsDialog() {
  const [open, setOpen] = useState(false)
  const [searchInput, setSearchInput] = useState("")
  const [selectedPlayer, setSelectedPlayer] = useState<PlayerPublic | null>(
    null,
  )
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const [matchMode, setMatchMode] = useState<AltMatchMode>("exact_ip")
  const [days, setDays] = useState(365)
  const [depth, setDepth] = useState(1)
  const [maxPlayersPerBucket, setMaxPlayersPerBucket] = useState(50)
  const searchBlurTimeoutRef = useRef<number | null>(null)
  const deferredSearchInput = useDeferredValue(searchInput)
  const playerSearchQuery = deferredSearchInput.trim()

  useEffect(() => {
    return () => {
      if (searchBlurTimeoutRef.current !== null) {
        window.clearTimeout(searchBlurTimeoutRef.current)
      }
    }
  }, [])

  const playerSearchQueryResult = useQuery({
    queryKey: ["admin-player-sessions", "alt-search", playerSearchQuery],
    queryFn: () =>
      PlayersService.searchPlayers({
        q: playerSearchQuery,
        offset: 0,
        limit: 8,
      }),
    enabled: open && selectedPlayer === null && playerSearchQuery.length > 0,
    staleTime: 30_000,
  })

  const lookupMutation = useMutation({
    mutationFn: () => {
      const steamid64 = selectedPlayer?.steamid64 ?? searchInput.trim()
      return AdminPlayerSessionsService.readAdminPlayerSessionIpLinks({
        steamid64,
        matchMode,
        days: clampInt(days, 1, 3650),
        depth: clampInt(depth, 1, 5),
        maxPlayersPerBucket: clampInt(maxPlayersPerBucket, 1, 500),
      })
    },
  })

  const searchResults = playerSearchQueryResult.data?.data ?? []
  const showSearchResults =
    isSearchFocused && selectedPlayer === null && playerSearchQuery.length > 0
  const lookupSteamid64 = selectedPlayer?.steamid64 ?? searchInput.trim()
  const canLookup = /^\d+$/.test(lookupSteamid64)

  const handleSelectPlayer = (player: PlayerPublic) => {
    setSelectedPlayer(player)
    setSearchInput(getPlayerDisplayName(player))
    setIsSearchFocused(false)
    lookupMutation.reset()
  }

  const clearSelectedPlayer = () => {
    setSelectedPlayer(null)
    setSearchInput("")
    setIsSearchFocused(false)
    lookupMutation.reset()
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm">
          <Users data-icon="inline-start" />
          Find Alts
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Find Alts</DialogTitle>
          <DialogDescription>
            Search player sessions by shared IP evidence.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-5">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_10rem_7rem_7rem_10rem] lg:items-end">
            <div className="flex flex-col gap-2">
              <label
                htmlFor="alt-player-search"
                className="text-sm font-medium"
              >
                Player
              </label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="alt-player-search"
                  aria-label="Search player for alt lookup"
                  value={searchInput}
                  onChange={(event) => {
                    if (searchBlurTimeoutRef.current !== null) {
                      window.clearTimeout(searchBlurTimeoutRef.current)
                    }
                    setSearchInput(event.target.value)
                    setIsSearchFocused(true)
                    setSelectedPlayer(null)
                    lookupMutation.reset()
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
                    if (event.key === "Enter") {
                      event.preventDefault()
                      if (searchResults.length > 0) {
                        handleSelectPlayer(searchResults[0])
                      } else if (canLookup) {
                        lookupMutation.mutate()
                      }
                    }
                    if (event.key === "Escape") {
                      setIsSearchFocused(false)
                    }
                  }}
                  placeholder="Search player or enter SteamID64"
                  className="pr-10 pl-9"
                />
                {selectedPlayer ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="absolute top-1/2 right-1 -translate-y-1/2"
                    onClick={clearSelectedPlayer}
                    aria-label="Clear selected player"
                  >
                    <X className="size-4" />
                  </Button>
                ) : null}
                {showSearchResults ? (
                  <div className="absolute top-[calc(100%+0.5rem)] right-0 left-0 z-20 overflow-hidden rounded-lg border bg-card shadow-lg">
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
                      <div className="flex flex-col py-1">
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

            <div className="flex flex-col gap-2">
              <label htmlFor="alt-match-mode" className="text-sm font-medium">
                Match
              </label>
              <Select
                value={matchMode}
                onValueChange={(value) => {
                  setMatchMode(value as AltMatchMode)
                  lookupMutation.reset()
                }}
              >
                <SelectTrigger id="alt-match-mode" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="exact_ip">Exact IP</SelectItem>
                    <SelectItem value="same_24">Same /24</SelectItem>
                    <SelectItem value="same_16_city">
                      Same /16 + city
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>

            <NumberField
              id="alt-depth"
              label="Depth"
              min={1}
              max={5}
              value={depth}
              onChange={(value) => {
                setDepth(value)
                lookupMutation.reset()
              }}
            />
            <NumberField
              id="alt-days"
              label="Days"
              min={1}
              max={3650}
              value={days}
              onChange={(value) => {
                setDays(value)
                lookupMutation.reset()
              }}
            />
            <NumberField
              id="alt-bucket-limit"
              label="Bucket limit"
              min={1}
              max={500}
              value={maxPlayersPerBucket}
              onChange={(value) => {
                setMaxPlayersPerBucket(value)
                lookupMutation.reset()
              }}
            />
          </div>

          {selectedPlayer ? (
            <div className="rounded-lg border bg-muted/30 px-3 py-2">
              <PlayerDisplay player={selectedPlayer} disableProfileLink />
            </div>
          ) : null}

          {lookupMutation.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Unable to find alts</AlertTitle>
              <AlertDescription>
                {getErrorMessage(lookupMutation.error)}
              </AlertDescription>
            </Alert>
          ) : null}

          {lookupMutation.data ? (
            <AltLookupResults result={lookupMutation.data} />
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen(false)}
          >
            Close
          </Button>
          <Button
            type="button"
            disabled={!canLookup || lookupMutation.isPending}
            onClick={() => lookupMutation.mutate()}
          >
            <Search data-icon="inline-start" />
            {lookupMutation.isPending ? "Searching..." : "Find Alts"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function NumberField({
  id,
  label,
  min,
  max,
  value,
  onChange,
}: {
  id: string
  label: string
  min: number
  max: number
  value: number
  onChange: (value: number) => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <Input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        onBlur={() => onChange(clampInt(value, min, max))}
      />
    </div>
  )
}

function AltLookupResults({
  result,
}: {
  result: AdminPlayerSessionIpLinksPublic
}) {
  const linkedPlayers = result.players.filter((row) => row.distance > 0)
  const maxDistance = result.players.reduce(
    (current, row) => Math.max(current, row.distance),
    0,
  )

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-2 sm:grid-cols-3">
        <SummaryBadge label="Linked players" value={linkedPlayers.length} />
        <SummaryBadge label="Max distance" value={maxDistance} />
        <SummaryBadge
          label="Skipped buckets"
          value={result.skipped_buckets.length}
        />
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">Players</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Player</TableHead>
              <TableHead>Distance</TableHead>
              <TableHead>Links</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.players.map((row) => (
              <TableRow key={row.player.steamid64}>
                <TableCell>
                  <PlayerDisplay player={row.player} />
                </TableCell>
                <TableCell>
                  <Badge variant={row.distance === 0 ? "secondary" : "outline"}>
                    {row.distance}
                  </Badge>
                </TableCell>
                <TableCell>{row.link_count ?? 0}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer text-sm font-semibold">
          Links ({result.links.length})
        </summary>
        <div className="mt-3">
          {result.links.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No linked players found.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>From</TableHead>
                  <TableHead>To</TableHead>
                  <TableHead>Bucket</TableHead>
                  <TableHead>Sessions</TableHead>
                  <TableHead>First seen</TableHead>
                  <TableHead>Last seen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.links.map((link) => (
                  <TableRow
                    key={`${link.from_steamid64}-${link.to_steamid64}-${link.bucket.key}`}
                  >
                    <TableCell className="font-mono text-xs">
                      {link.from_steamid64}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {link.to_steamid64}
                    </TableCell>
                    <TableCell>{link.bucket.label}</TableCell>
                    <TableCell>
                      {link.session_count_from} / {link.session_count_to}
                    </TableCell>
                    <TableCell>
                      <FormattedDateTime value={link.first_seen_at} />
                    </TableCell>
                    <TableCell>
                      <FormattedDateTime value={link.last_seen_at} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </details>

      {result.skipped_buckets.length > 0 ? (
        <details className="rounded-lg border p-3">
          <summary className="cursor-pointer text-sm font-semibold">
            Skipped buckets ({result.skipped_buckets.length})
          </summary>
          <div className="mt-3">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Bucket</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Players</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.skipped_buckets.map((row) => (
                  <TableRow key={row.bucket.key}>
                    <TableCell>{row.bucket.label}</TableCell>
                    <TableCell>Too many players</TableCell>
                    <TableCell>{row.player_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </details>
      ) : null}
    </div>
  )
}

function SummaryBadge({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border bg-muted/30 px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold">{value.toLocaleString()}</div>
    </div>
  )
}

function getPlayerDisplayName(player: PlayerPublic) {
  return player.alias || player.name || player.steamid64
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message
  }
  return "The lookup failed."
}

function clampInt(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) {
    return min
  }
  return Math.min(max, Math.max(min, Math.trunc(value)))
}

function toSessionSortBy(id: string): SessionSortBy {
  if (id === "disconnect_at" || id === "duration_seconds") {
    return id
  }
  return "connected_at"
}

function SortableHeader({
  column,
  label,
}: {
  column: {
    getIsSorted: () => false | "asc" | "desc"
    toggleSorting: (desc?: boolean) => void
  }
  label: string
}) {
  const sorted = column.getIsSorted()
  return (
    <button
      type="button"
      className="-mx-2 -my-1 inline-flex items-center gap-1 rounded-md px-2 py-1 text-left text-sm font-medium hover:bg-accent"
      onClick={() => column.toggleSorting(sorted === "asc")}
    >
      {label}
      {sorted === "asc" ? <ArrowUp className="size-3" /> : null}
      {sorted === "desc" ? <ArrowDown className="size-3" /> : null}
    </button>
  )
}
