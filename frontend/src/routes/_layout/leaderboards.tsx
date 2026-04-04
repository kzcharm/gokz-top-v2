import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import {
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { useMemo, useState } from "react"

import { LeaderboardsService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import ErrorComponent from "@/components/Common/ErrorComponent"
import { columns } from "@/components/Leaderboards/columns"
import { useScope } from "@/components/scope-provider"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { getPageTitle } from "@/lib/site"

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

function LeaderboardsSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-32 rounded-[28px]" />
      <Skeleton className="h-[520px] rounded-[28px]" />
    </div>
  )
}

function LeaderboardsRoute() {
  const { scope } = useScope()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [sorting, setSorting] = useState<SortingState>([
    { id: "rating", desc: true },
  ])

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

  if (leaderboardQuery.isLoading) {
    return <LeaderboardsSkeleton />
  }

  if (leaderboardQuery.isError) {
    return <ErrorComponent />
  }

  return (
    <div className="space-y-6">
      <Card className="gap-0 overflow-hidden rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="space-y-3 p-6 sm:p-8">
          <h1 className="text-3xl font-semibold tracking-tight">Leaderboards</h1>
        </CardContent>
      </Card>

      <Card className="gap-0 overflow-hidden rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0">
          <DataTable
            columns={columns}
            data={tableData}
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
