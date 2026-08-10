import { useQuery } from "@tanstack/react-query"
import {
  type ColumnDef,
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { ArrowDown, ArrowUp, Info, LoaderCircle, Plus } from "lucide-react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  type CountryLeaderboardEntryPublic,
  LeaderboardsService,
  type ModeScope,
} from "@/client"
import { CountryFlag, getCountryName } from "@/components/Common/CountryFlag"
import { DataTable } from "@/components/Common/DataTable"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { formatNumber } from "@/i18n/locale"
import { extractErrorMessage } from "@/utils"

function rating(value: number | null) {
  return value === null ? "N/A" : value.toFixed(2)
}

type CountryMetric =
  | "ranked_players"
  | "active_players"
  | "top10_percentile_rating"
  | "top10_average_rating"

function metricColumn(
  key: CountryMetric,
  title: string,
  options?: { tooltip?: string },
): ColumnDef<CountryLeaderboardEntryPublic> {
  return {
    accessorKey: key,
    size:
      key === "top10_percentile_rating"
        ? 195
        : key === "top10_average_rating"
          ? 165
          : key === "active_players"
            ? 170
            : 150,
    header: ({ column }) => {
      const sorting = column.getIsSorted()
      return (
        <div className="flex w-full justify-center">
          <button
            type="button"
            className="inline-flex min-h-8 h-auto items-center justify-center gap-1 rounded-md px-2 py-1 text-center text-xs font-semibold uppercase tracking-wider transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            onClick={() => column.toggleSorting(sorting !== "desc")}
          >
            {options?.tooltip ? (
              <Tooltip delayDuration={250}>
                <TooltipTrigger asChild>
                  <span className="inline-flex min-w-0 items-center justify-center gap-1">
                    <span className="whitespace-normal leading-tight">
                      {title}
                    </span>
                    <Info
                      className="size-3.5 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                  </span>
                </TooltipTrigger>
                <TooltipContent sideOffset={6}>
                  {options.tooltip}
                </TooltipContent>
              </Tooltip>
            ) : (
              <span className="whitespace-normal leading-tight">{title}</span>
            )}
            {sorting === "desc" ? (
              <ArrowDown className="size-3.5 shrink-0" aria-hidden="true" />
            ) : sorting === "asc" ? (
              <ArrowUp className="size-3.5 shrink-0" aria-hidden="true" />
            ) : null}
          </button>
        </div>
      )
    },
    cell: ({ row }) => (
      <div className="flex w-full justify-center font-medium tabular-nums">
        {key === "top10_percentile_rating" || key === "top10_average_rating"
          ? rating(row.original[key])
          : formatNumber(row.original[key])}
      </div>
    ),
  }
}

function sortCountryRows(
  rows: CountryLeaderboardEntryPublic[],
  sorting: SortingState,
) {
  const sort = sorting[0]
  if (!sort) return rows
  const key = sort.id as CountryMetric
  const sortedRows = [...rows].sort((left, right) => {
    const leftValue = left[key] ?? Number.NEGATIVE_INFINITY
    const rightValue = right[key] ?? Number.NEGATIVE_INFINITY
    const comparison = Number(leftValue) - Number(rightValue)
    if (comparison !== 0) return sort.desc ? -comparison : comparison
    return (left.country ?? "").localeCompare(right.country ?? "")
  })
  let rankedPosition = 0
  return sortedRows.map((row) => ({
    ...row,
    rank: row.rank === null ? null : ++rankedPosition,
  }))
}

function CountryTopPlayersMenu({
  country,
  scope,
  t,
}: {
  country: string
  scope: ModeScope
  t: ReturnType<typeof useTranslation>["t"]
}) {
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: ["leaderboards", "country-players", scope, country],
    queryFn: () =>
      LeaderboardsService.readPlayerLeaderboard({
        country,
        scope,
        offset: 3,
        limit: 7,
        sortBy: "rating",
        sortOrder: "desc",
      }),
    enabled: open,
    staleTime: 30_000,
  })

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={t("leaderboards.countries.viewTopPlayers")}
        >
          <Plus aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={8}
        className="max-h-[min(28rem,calc(100vh-2rem))] min-w-[15rem] overflow-y-auto p-2"
      >
        {query.isLoading ? (
          <div className="flex justify-center px-3 py-4 text-muted-foreground">
            <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          </div>
        ) : query.data?.data.length ? (
          <div className="space-y-1">
            {query.data.data.map((entry) => (
              <div
                key={entry.player.steamid64}
                className="flex min-w-0 items-center gap-2 px-1 py-1"
              >
                <span className="w-5 shrink-0 text-right text-xs font-semibold tabular-nums text-muted-foreground">
                  {entry.rank}
                </span>
                <PlayerDisplay
                  player={{
                    steamid64: entry.player.steamid64,
                    displayName: entry.player.display_name,
                    name: entry.player.display_name,
                  }}
                  scope={scope}
                  showCountryFlag={false}
                  className="min-w-0"
                />
              </div>
            ))}
          </div>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function CountriesLeaderboardTab() {
  const { t, i18n } = useTranslation()
  const { scope } = useScope()
  const [sorting, setSorting] = useState<SortingState>([
    { id: "top10_average_rating", desc: true },
  ])
  const query = useQuery({
    queryKey: ["leaderboards", "countries", scope],
    queryFn: () =>
      LeaderboardsService.readCountryLeaderboard({
        scope,
        offset: 0,
        limit: 200,
      }),
    staleTime: 30_000,
  })
  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    setSorting(next.length ? [next[0]] : sorting)
  }
  const rows = useMemo(
    () => sortCountryRows(query.data?.data ?? [], sorting),
    [query.data?.data, sorting],
  )
  const columns = useMemo<ColumnDef<CountryLeaderboardEntryPublic>[]>(
    () => [
      {
        accessorKey: "rank",
        size: 56,
        header: () => <div className="flex w-full justify-center">#</div>,
        cell: ({ row }) => (
          <div className="flex w-full justify-center font-semibold tabular-nums">
            {row.original.rank === null ? "-" : formatNumber(row.original.rank)}
          </div>
        ),
      },
      {
        accessorKey: "country",
        size: 140,
        header: () => (
          <Tooltip delayDuration={250}>
            <TooltipTrigger asChild>
              <span className="inline-flex items-center gap-1">
                {t("leaderboards.countries.country")}
                <Info
                  className="size-3.5 text-muted-foreground"
                  aria-hidden="true"
                />
              </span>
            </TooltipTrigger>
            <TooltipContent sideOffset={6}>
              {t("leaderboards.countries.countryTooltip")}
            </TooltipContent>
          </Tooltip>
        ),
        cell: ({ row }) => (
          <div className="flex items-center gap-3">
            <CountryFlag countryCode={row.original.country} />
            <span className="truncate">
              {getCountryName(row.original.country, i18n.resolvedLanguage) ??
                row.original.country}
            </span>
          </div>
        ),
      },
      metricColumn(
        "top10_average_rating",
        t("leaderboards.countries.top10AverageRating"),
      ),
      metricColumn(
        "top10_percentile_rating",
        t("leaderboards.countries.top10PercentileRating"),
        { tooltip: t("leaderboards.countries.top10PercentileRatingTooltip") },
      ),
      metricColumn("ranked_players", t("leaderboards.countries.rankedPlayers")),
      metricColumn(
        "active_players",
        t("leaderboards.countries.activePlayers"),
        { tooltip: t("leaderboards.countries.activePlayersTooltip") },
      ),
      {
        accessorKey: "top_players",
        size: 560,
        header: () => t("leaderboards.countries.topPlayers"),
        cell: ({ row }) => (
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid min-w-0 flex-1 grid-cols-3 gap-3">
              {row.original.top_players.map((player) => (
                <div key={player.steamid64} className="min-w-0">
                  <PlayerDisplay
                    player={{
                      steamid64: player.steamid64,
                      displayName: player.display_name,
                      name: player.display_name,
                    }}
                    scope={scope}
                    showCountryFlag={false}
                    className="min-w-0"
                  />
                </div>
              ))}
            </div>
            {row.original.country ? (
              <CountryTopPlayersMenu
                country={row.original.country}
                scope={scope}
                t={t}
              />
            ) : null}
          </div>
        ),
      },
    ],
    [i18n.resolvedLanguage, t, scope],
  )

  return (
    <div className="space-y-6">
      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 sm:px-8">
          <h2 className="text-lg font-semibold">
            {t("leaderboards.countries.title")}
          </h2>
        </CardContent>
      </Card>
      {query.isError ? (
        <Alert variant="destructive">
          <AlertTitle>{t("leaderboards.countries.loadFailedTitle")}</AlertTitle>
          <AlertDescription>
            {extractErrorMessage(query.error)}
          </AlertDescription>
        </Alert>
      ) : null}
      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
          <DataTable
            columns={columns}
            data={rows}
            isLoading={query.isLoading}
            emptyText={t("leaderboards.countries.empty")}
            tableContainerClassName="overflow-x-auto md:overflow-visible"
            tableClassName="table-fixed min-w-[1411px] border-separate border-spacing-0"
            showFooter={false}
            disablePagination
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
