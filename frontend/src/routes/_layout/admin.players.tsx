import { useQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import {
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { useDeferredValue, useMemo, useState } from "react"

import { type PlayerPublic, PlayersService, UsersService } from "@/client"
import { columns } from "@/components/AdminPlayers/columns"
import { DataTable } from "@/components/Common/DataTable"
import PendingUsers from "@/components/Pending/PendingUsers"
import { Input } from "@/components/ui/input"
import { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/admin/players")({
  component: AdminPlayers,
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
        title: getPageTitle(),
      },
    ],
  }),
})

function AdminPlayers() {
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [searchInput, setSearchInput] = useState("")
  const [sorting, setSorting] = useState<SortingState>([
    { id: "created_at", desc: true },
  ])
  const deferredSearchInput = useDeferredValue(searchInput)
  const normalizedSearch = deferredSearchInput.trim()

  const sortBy =
    sorting[0]?.id === "last_played_at" ? "last_played_at" : "created_at"
  const sortOrder = sorting[0]?.desc ? "desc" : "asc"
  const isSearchMode = normalizedSearch.length > 0

  const { data, isLoading } = useQuery({
    queryFn: () =>
      PlayersService.readPlayers({
        offset: pageIndex * pageSize,
        limit: pageSize,
        sortBy,
        sortOrder,
      }),
    queryKey: ["players", pageIndex, pageSize, sortBy, sortOrder],
    enabled: !isSearchMode,
  })

  const { data: searchPlayers, isLoading: isSearchLoading } = useQuery({
    queryFn: () =>
      PlayersService.searchPlayers({
        q: normalizedSearch,
        offset: 0,
        limit: 50,
      }),
    queryKey: ["player-search", normalizedSearch],
    enabled: isSearchMode,
  })

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    const nextSort =
      next.length > 0 ? [next[0]] : [{ id: "created_at", desc: true }]
    setSorting(nextSort)
    setPageIndex(0)
  }

  const tableData = useMemo(() => data?.data ?? [], [data])
  const searchTableData = useMemo(() => {
    if (!searchPlayers) {
      return []
    }

    return [...searchPlayers.data].sort((left, right) =>
      comparePlayers({
        left,
        right,
        sortBy,
        sortOrder,
      }),
    )
  }, [searchPlayers, sortBy, sortOrder])

  const visibleTableData = isSearchMode
    ? searchTableData.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize)
    : tableData
  const totalCount = isSearchMode
    ? searchTableData.length
    : (data?.count ?? 0)
  const isTableLoading = isSearchMode ? isSearchLoading : isLoading

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Players{" "}
            <span className="text-base font-medium text-muted-foreground">
              (Total {totalCount.toLocaleString()})
            </span>
          </h1>
        </div>
        <Input
          aria-label="Search players"
          className="w-full sm:w-80"
          placeholder="Search players..."
          value={searchInput}
          onChange={(event) => {
            setSearchInput(event.target.value)
            setPageIndex(0)
          }}
        />
      </div>
      {isTableLoading ? (
        <PendingUsers />
      ) : (
        <DataTable
          columns={columns}
          data={visibleTableData}
          emptyText={
            isSearchMode ? "No players matched your search." : "No results found."
          }
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

function comparePlayers({
  left,
  right,
  sortBy,
  sortOrder,
}: {
  left: PlayerPublic
  right: PlayerPublic
  sortBy: "created_at" | "last_played_at"
  sortOrder: "asc" | "desc"
}) {
  const leftValue = toComparableTime(left[sortBy])
  const rightValue = toComparableTime(right[sortBy])

  if (leftValue === null && rightValue === null) {
    return Number(right.steamid64) - Number(left.steamid64)
  }
  if (leftValue === null) {
    return 1
  }
  if (rightValue === null) {
    return -1
  }
  if (leftValue !== rightValue) {
    return sortOrder === "asc" ? leftValue - rightValue : rightValue - leftValue
  }

  return Number(right.steamid64) - Number(left.steamid64)
}

function toComparableTime(value: string | Date | null | undefined) {
  if (!value) {
    return null
  }

  const date = value instanceof Date ? value : new Date(value)
  const timestamp = date.getTime()
  return Number.isNaN(timestamp) ? null : timestamp
}
