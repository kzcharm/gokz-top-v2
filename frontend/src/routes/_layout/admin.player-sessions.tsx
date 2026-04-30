import { useQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import {
  type ColumnDef,
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { ArrowDown, ArrowUp } from "lucide-react"
import { useMemo, useState } from "react"

import {
  type AdminPlayerSessionPublic,
  AdminPlayerSessionsService,
  UsersService,
} from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import PendingUsers from "@/components/Pending/PendingUsers"
import { formatTimerTime } from "@/components/Servers/utils"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"

type SessionSortBy = "connected_at" | "disconnect_at" | "duration_seconds"

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
    if (!user.is_superuser) {
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
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold tracking-tight">
          Player Sessions{" "}
          <span className="text-base font-medium text-muted-foreground">
            (Total {totalCount.toLocaleString()})
          </span>
        </h1>
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

      {query.isLoading ? (
        <PendingUsers />
      ) : (
        <DataTable
          columns={columns}
          data={query.data?.data ?? []}
          emptyText="No player sessions found."
          footerSummary={<span />}
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
      )}
    </div>
  )
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
