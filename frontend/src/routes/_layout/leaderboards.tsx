import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import {
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { LocateFixed } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

import { LeaderboardsService } from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { DataTable } from "@/components/Common/DataTable"
import ErrorComponent from "@/components/Common/ErrorComponent"
import { columns } from "@/components/Leaderboards/columns"
import { useScope } from "@/components/scope-provider"
import { Card, CardContent } from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import useAuth from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"
import { cn } from "@/lib/utils"

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
  const { user: currentUser } = useAuth()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [isFindingMe, setIsFindingMe] = useState(false)
  const [pendingSpotlightSteamid64, setPendingSpotlightSteamid64] = useState<
    string | null
  >(null)
  const [sorting, setSorting] = useState<SortingState>([
    { id: "rating", desc: true },
  ])
  const spotlightTimeoutRef = useRef<number | null>(null)
  const spotlightStartTimeoutRef = useRef<number | null>(null)

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

  useEffect(() => {
    return () => {
      if (spotlightStartTimeoutRef.current !== null) {
        window.clearTimeout(spotlightStartTimeoutRef.current)
      }
      if (spotlightTimeoutRef.current !== null) {
        window.clearTimeout(spotlightTimeoutRef.current)
      }
    }
  }, [])

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

  const handleFindMe = async () => {
    if (!currentUser?.steamid64) {
      return
    }

    setIsFindingMe(true)

    try {
      const token = localStorage.getItem("access_token")
      const response = await fetch(
        `${OpenAPI.BASE}/v1/leaderboards/players/${encodeURIComponent(currentUser.steamid64)}?scope=${scope}`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        },
      )

      if (!response.ok) {
        throw new Error("Failed to fetch leaderboard rank")
      }

      const data = (await response.json()) as { rank?: number | null }
      if (!data.rank) {
        toast.error("You are not ranked yet", {
          description: "Complete more runs in this scope before using Find Me.",
        })
        return
      }

      setSorting([{ id: "rating", desc: true }])
      setPendingSpotlightSteamid64(currentUser.steamid64)
      setPageIndex(Math.floor((data.rank - 1) / pageSize))
    } catch {
      toast.error("Could not find your leaderboard position", {
        description: "Try again in a moment.",
      })
    } finally {
      setIsFindingMe(false)
    }
  }

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
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <h1 className="text-3xl font-semibold tracking-tight">
              Leaderboards
            </h1>
            <LoadingButton
              type="button"
              variant="outline"
              loading={isFindingMe}
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
