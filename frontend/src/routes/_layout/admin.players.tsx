import { useQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import {
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { useMemo, useState } from "react"

import { PlayersService, UsersService } from "@/client"
import { columns } from "@/components/AdminPlayers/columns"
import { DataTable } from "@/components/Common/DataTable"
import PendingUsers from "@/components/Pending/PendingUsers"

export const Route = createFileRoute("/_layout/admin/players")({
  component: AdminPlayers,
  beforeLoad: async () => {
    const user = await UsersService.readUserMe()
    if (!user.is_superuser) {
      throw redirect({
        to: "/",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: "GOKZ TOP",
      },
    ],
  }),
})

function AdminPlayers() {
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [sorting, setSorting] = useState<SortingState>([
    { id: "created_at", desc: true },
  ])

  const sortBy =
    sorting[0]?.id === "last_played_at" ? "last_played_at" : "created_at"
  const sortOrder = sorting[0]?.desc ? "desc" : "asc"

  const { data, isLoading } = useQuery({
    queryFn: () =>
      PlayersService.readPlayers({
        offset: pageIndex * pageSize,
        limit: pageSize,
        sortBy,
        sortOrder,
      }),
    queryKey: ["players", pageIndex, pageSize, sortBy, sortOrder],
  })

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    const nextSort =
      next.length > 0 ? [next[0]] : [{ id: "created_at", desc: true }]
    setSorting(nextSort)
    setPageIndex(0)
  }

  const tableData = useMemo(() => data?.data ?? [], [data])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Players</h1>
        <p className="text-muted-foreground">
          all Steam Players (who has played or potentially will play kz ( some
          mapper doesn't even played once, but we need to ensure them here)
        </p>
      </div>
      {isLoading ? (
        <PendingUsers />
      ) : (
        <DataTable
          columns={columns}
          data={tableData}
          serverPagination={{
            pageIndex,
            pageSize,
            totalCount: data?.count ?? 0,
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
