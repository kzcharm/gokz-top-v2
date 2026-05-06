import { useQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import {
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { useDeferredValue, useMemo, useState } from "react"

import { PlayersService, type UserPublic, UsersService } from "@/client"
import {
  AdminControlsCard,
  AdminPageHeader,
  AdminTableCard,
} from "@/components/Admin/AdminPageLayout"
import { columns, type UserTableData } from "@/components/Admin/columns"
import { DataTable } from "@/components/Common/DataTable"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { Input } from "@/components/ui/input"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"
import { isSuperuser } from "@/lib/user-roles"

export const Route = createFileRoute("/_layout/admin/users")({
  component: AdminUsers,
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
        title: getPageTitle(),
      },
    ],
  }),
})

function AdminUsers() {
  const { user: currentUser } = useAuth()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [searchInput, setSearchInput] = useState("")
  const [sorting, setSorting] = useState<SortingState>([
    { id: "last_visited_at", desc: true },
  ])
  const deferredSearchInput = useDeferredValue(searchInput)
  const normalizedSearch = deferredSearchInput.trim()

  const sortBy =
    sorting[0]?.id === "last_visited_at" ? "last_visited_at" : "created_at"
  const sortOrder = sorting[0]?.desc ? "desc" : "asc"
  const isSearchMode = normalizedSearch.length > 0

  const { data, isLoading } = useQuery({
    queryFn: () =>
      UsersService.readUsers({
        skip: pageIndex * pageSize,
        limit: pageSize,
        sortBy,
        sortOrder,
      }),
    queryKey: ["users", pageIndex, pageSize, sortBy, sortOrder],
    enabled: !isSearchMode,
  })

  const { data: searchUsers, isLoading: isSearchLoading } = useQuery({
    queryFn: async () => {
      const playerResults = await PlayersService.searchPlayers({
        q: normalizedSearch,
        offset: 0,
        limit: 50,
      })

      const users = await Promise.all(
        playerResults.data.map(async (player) => {
          try {
            return await UsersService.readUserById({
              userId: player.steamid64,
            })
          } catch {
            return null
          }
        }),
      )

      return users.filter((user): user is UserPublic => user !== null)
    },
    queryKey: ["user-search", normalizedSearch],
    enabled: isSearchMode,
  })

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    const nextSort =
      next.length > 0 ? [next[0]] : [{ id: "last_visited_at", desc: true }]
    setSorting(nextSort)
    setPageIndex(0)
  }

  const searchTableData = useMemo<UserTableData[]>(() => {
    if (!searchUsers) {
      return []
    }

    const sortedUsers = [...searchUsers].sort((left, right) =>
      compareUsers({
        left,
        right,
        sortBy,
        sortOrder,
      }),
    )

    return sortedUsers.map((user) => ({
      ...user,
      isCurrentUser: currentUser?.steamid64 === user.steamid64,
    }))
  }, [currentUser?.steamid64, searchUsers, sortBy, sortOrder])

  const tableData = useMemo<UserTableData[]>(
    () =>
      (data?.data ?? []).map((user: UserPublic) => ({
        ...user,
        isCurrentUser: currentUser?.steamid64 === user.steamid64,
      })),
    [data?.data, currentUser?.steamid64],
  )

  const visibleTableData = isSearchMode
    ? searchTableData.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize)
    : tableData
  const totalCount = isSearchMode ? searchTableData.length : (data?.count ?? 0)
  const isTableLoading = isSearchMode ? isSearchLoading : isLoading

  return (
    <div className="flex flex-col gap-6">
      <AdminPageHeader title="Users" />
      <AdminControlsCard>
        <Input
          aria-label="Search users"
          className="w-full sm:w-80"
          placeholder="Search players..."
          value={searchInput}
          onChange={(event) => {
            setSearchInput(event.target.value)
            setPageIndex(0)
          }}
        />
      </AdminControlsCard>
      <AdminTableCard>
        <DataTable
          columns={columns}
          data={visibleTableData}
          isLoading={isTableLoading}
          stickyHeader
          stickyHeaderTopClassName="top-16"
          tableContainerClassName="md:overflow-visible"
          tableClassName="border-separate border-spacing-0"
          showFooter={false}
          emptyText={
            isSearchMode ? "No users matched your search." : "No results found."
          }
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
          totalLabel="Users"
          totalCount={totalCount}
          pageIndex={pageIndex}
          pageCount={Math.max(1, Math.ceil(totalCount / pageSize))}
          pageSize={pageSize}
          onPageIndexChange={setPageIndex}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPageIndex(0)
          }}
          hasExactCount={!isTableLoading}
          isTotalCountLoading={isTableLoading}
        />
      </AdminTableCard>
    </div>
  )
}

function compareUsers({
  left,
  right,
  sortBy,
  sortOrder,
}: {
  left: UserPublic
  right: UserPublic
  sortBy: "created_at" | "last_visited_at"
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
