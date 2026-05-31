import { useQuery } from "@tanstack/react-query"
import {
  type ColumnDef,
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  type CommunityLeaderboardEntryPublic,
  LeaderboardsService,
} from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import {
  PlayerDisplay,
  type PlayerDisplayPlayer,
} from "@/components/Common/PlayerDisplay"
import { SortableHeader } from "@/components/Leaderboards/columns"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import { formatNumber } from "@/i18n/locale"
import { fetchPlayersForDisplay } from "@/lib/player-graphql"
import { extractErrorMessage } from "@/utils"

type CommunitySortBy =
  | "views_count"
  | "unique_visitors"
  | "likes"
  | "unique_likers"

type CommunityLeaderboardTableRow = CommunityLeaderboardEntryPublic & {
  playerData: PlayerDisplayPlayer
}

type CommunityMetricColumn = {
  value: CommunitySortBy
  labelKey: string
  size: number
}

const COMMUNITY_METRIC_COLUMNS: readonly CommunityMetricColumn[] = [
  {
    value: "views_count",
    labelKey: "leaderboards.community.metrics.viewsCount",
    size: 132,
  },
  {
    value: "unique_visitors",
    labelKey: "leaderboards.community.metrics.uniqueVisitors",
    size: 154,
  },
  {
    value: "likes",
    labelKey: "leaderboards.community.metrics.likes",
    size: 104,
  },
  {
    value: "unique_likers",
    labelKey: "leaderboards.community.metrics.uniqueLikers",
    size: 136,
  },
] as const

function isCommunitySortBy(
  value: string | undefined,
): value is CommunitySortBy {
  return COMMUNITY_METRIC_COLUMNS.some((column) => column.value === value)
}

function getCommunityLeaderboardColumns({
  t,
  playerLabel,
}: {
  t: ReturnType<typeof useTranslation>["t"]
  playerLabel: string
}): ColumnDef<CommunityLeaderboardTableRow>[] {
  return [
    {
      accessorKey: "rank",
      size: 56,
      header: () => <div className="flex w-full justify-center">#</div>,
      cell: ({ row }) => (
        <div className="flex w-full justify-center">
          <span className="font-semibold tabular-nums">
            {formatNumber(row.original.rank)}
          </span>
        </div>
      ),
    },
    {
      accessorKey: "player",
      size: 240,
      header: () => playerLabel,
      cell: ({ row }) => <PlayerDisplay player={row.original.playerData} />,
    },
    ...COMMUNITY_METRIC_COLUMNS.map(
      (column): ColumnDef<CommunityLeaderboardTableRow> => ({
        accessorKey: column.value,
        size: column.size,
        header: ({ column: tableColumn }) => (
          <SortableHeader
            title={t(column.labelKey)}
            column={tableColumn}
            align="center"
          />
        ),
        cell: ({ row }) => (
          <div className="flex w-full justify-center">
            <span className="font-semibold tabular-nums">
              {formatNumber(row.original[column.value])}
            </span>
          </div>
        ),
      }),
    ),
  ]
}

export function CommunityLeaderboardTab() {
  const { t } = useTranslation()
  const [sorting, setSorting] = useState<SortingState>([
    { id: "views_count", desc: true },
  ])
  const sortBy = isCommunitySortBy(sorting[0]?.id)
    ? sorting[0].id
    : "views_count"

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    const nextSort = [
      {
        id: isCommunitySortBy(next[0]?.id)
          ? next[0].id
          : (sorting[0]?.id ?? "views_count"),
        desc: true,
      },
    ]
    setSorting(nextSort)
  }

  const communityQuery = useQuery({
    queryKey: ["leaderboards", "community", sortBy],
    queryFn: () =>
      LeaderboardsService.readCommunityLeaderboard({
        sortBy,
        offset: 0,
        limit: 100,
        includeCount: false,
      }),
    placeholderData: (previousData) => previousData,
    staleTime: 30_000,
  })

  const entries = useMemo(
    () => communityQuery.data?.data ?? [],
    [communityQuery.data],
  )
  const playerSteamid64s = useMemo(
    () => entries.map((entry) => entry.player.steamid64),
    [entries],
  )
  const playersQuery = useQuery({
    queryKey: ["graphql", "players", "community-leaderboard", playerSteamid64s],
    enabled: playerSteamid64s.length > 0,
    queryFn: () => fetchPlayersForDisplay(playerSteamid64s, "OVR"),
    staleTime: 30_000,
  })
  const playersBySteamid64 = useMemo(() => {
    const players = new Map<string, PlayerDisplayPlayer>()
    for (const player of playersQuery.data ?? []) {
      if (player) {
        players.set(player.steamid64, player)
      }
    }
    return players
  }, [playersQuery.data])

  const tableData = useMemo<CommunityLeaderboardTableRow[]>(
    () =>
      entries.map((entry) => {
        const hydratedPlayer = playersBySteamid64.get(entry.player.steamid64)
        return {
          ...entry,
          playerData: hydratedPlayer ?? {
            steamid64: entry.player.steamid64,
            displayName: entry.player.display_name,
            name: entry.player.display_name,
          },
        }
      }),
    [entries, playersBySteamid64],
  )
  const columns = useMemo(
    () =>
      getCommunityLeaderboardColumns({
        t,
        playerLabel: t("labels.player"),
      }),
    [t],
  )

  return (
    <div className="space-y-6">
      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 sm:px-8">
          <div>
            <h2 className="text-lg font-semibold tracking-normal">
              {t("leaderboards.community.title")}
            </h2>
          </div>
        </CardContent>
      </Card>

      {communityQuery.isError ? (
        <Alert variant="destructive">
          <AlertTitle>{t("leaderboards.community.loadFailedTitle")}</AlertTitle>
          <AlertDescription>
            {extractErrorMessage(communityQuery.error)}
          </AlertDescription>
        </Alert>
      ) : null}

      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
          <DataTable
            columns={columns}
            data={tableData}
            isLoading={communityQuery.isLoading}
            emptyText={t("leaderboards.community.empty")}
            stickyHeader
            stickyHeaderTopClassName="top-16"
            tableContainerClassName="overflow-x-auto md:overflow-visible"
            tableClassName="min-w-[820px] border-separate border-spacing-0"
            showFooter={false}
            serverPagination={{
              pageIndex: 0,
              pageSize: 100,
              totalCount: tableData.length,
              onPageChange: () => undefined,
              onPageSizeChange: () => undefined,
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
