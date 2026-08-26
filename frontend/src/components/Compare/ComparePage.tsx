import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import type { EChartsOption, EChartsType } from "echarts"
import * as echarts from "echarts"
import { ArrowLeftRight, LoaderCircle } from "lucide-react"
import { startTransition, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import type { PlayerCompareRunPublic, PlayerComparisonPublic } from "@/client"
import { PlayersService } from "@/client"
import { CountryFlag } from "@/components/Common/CountryFlag"
import { getMapImageUrls, MapDisplay } from "@/components/Common/MapDisplay"
import { PlayerSearchSelect } from "@/components/Common/PlayerSearchSelect"
import { formatRating } from "@/components/Profile/profile-utils"
import { ModeBadge } from "@/components/Records/ModeBadge"
import { PointsBadge } from "@/components/Records/PointsBadge"
import { TeleportsBadge } from "@/components/Records/TeleportsBadge"
import { formatRecordTime } from "@/components/Records/utils"
import { TierBadge } from "@/components/Servers/TierBadge"
import { useScope } from "@/components/scope-provider"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  fetchPlayerByIdentifier,
  type GraphqlPlayer,
} from "@/lib/player-graphql"
import {
  getHighestPlayerPermission,
  PLAYER_PERMISSION_RING_CLASS_NAMES,
} from "@/lib/user-roles"
import { cn } from "@/lib/utils"
import { getInitials } from "@/utils"

const PAGE_SIZE = 50

async function fetchComparison({
  player1,
  player2,
  scope,
}: {
  player1: string
  player2: string
  scope: "OVR" | "KZT" | "SKZ" | "VNL"
}): Promise<PlayerComparisonPublic> {
  return await PlayersService.readPlayerComparison({
    player1,
    player2,
    scope,
  })
}

function formatMetric(value: number | null | undefined) {
  return value == null ? "-" : new Intl.NumberFormat("en-US").format(value)
}

function formatDelta(value: number | null | undefined) {
  if (value == null) {
    return "-"
  }
  return `${value < 0 ? "-" : "+"}${formatRecordTime(Math.abs(value))}`
}

function ComparisonRadar({
  comparison,
  player1Name,
  player2Name,
}: {
  comparison: PlayerComparisonPublic
  player1Name: string
  player2Name: string
}) {
  const { t } = useTranslation()
  const chartElementRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<EChartsType | null>(null)

  useEffect(() => {
    const element = chartElementRef.current
    if (!element) {
      return
    }
    const chart = echarts.init(element, undefined, { renderer: "canvas" })
    chartRef.current = chart
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(element)
    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) {
      return
    }
    const values = comparison.progression
    const option: EChartsOption = {
      color: ["#0f9d8b", "#e8792f"],
      legend: { bottom: 0, data: [player1Name, player2Name] },
      radar: {
        // With eight evenly-spaced indicators, this places Tier 8 at 6 o'clock.
        startAngle: 315,
        indicator: values.map((tier) => ({
          name: `${t("compare.tier")} ${tier.tier}`,
          max: 100,
        })),
        splitNumber: 4,
        axisName: { color: "#737373" },
        splitLine: { lineStyle: { color: "rgba(128, 128, 128, 0.25)" } },
        splitArea: { show: false },
        axisLine: { lineStyle: { color: "rgba(128, 128, 128, 0.3)" } },
      },
      series: [
        {
          type: "radar",
          symbol: "none",
          data: [
            {
              name: player1Name,
              value: values.map((tier) =>
                tier.total_maps === 0
                  ? 0
                  : (tier.player1_finished / tier.total_maps) * 100,
              ),
              areaStyle: { opacity: 0.14 },
            },
            {
              name: player2Name,
              value: values.map((tier) =>
                tier.total_maps === 0
                  ? 0
                  : (tier.player2_finished / tier.total_maps) * 100,
              ),
              areaStyle: { opacity: 0.14 },
            },
          ],
        },
      ],
      tooltip: {
        formatter: (params) => {
          const item = Array.isArray(params) ? params[0] : params
          const values = Array.isArray(item.value) ? item.value : []
          return values
            .map(
              (value, index) =>
                `${t("compare.tier")} ${index + 1}: ${Number(value).toFixed(1)}%`,
            )
            .join("<br />")
        },
      },
    }
    chart.setOption(option, true)
  }, [comparison.progression, player1Name, player2Name, t])

  return (
    <div
      ref={chartElementRef}
      className="aspect-square min-h-72 w-full max-h-[34rem]"
      role="img"
      aria-label={t("compare.progressionAria", {
        player1: player1Name,
        player2: player2Name,
      })}
    />
  )
}

function EmptyRunCell() {
  return <span className="text-muted-foreground">-</span>
}

function TimeDelta({ value }: { value: number | null | undefined }) {
  if (value == null) {
    return <EmptyRunCell />
  }

  return (
    <span
      className={cn(
        "block text-right font-mono font-medium tabular-nums",
        value < 0
          ? "text-emerald-600 dark:text-emerald-400"
          : value > 0
            ? "text-red-600 dark:text-red-400"
            : "text-muted-foreground",
      )}
    >
      {formatDelta(value)}
    </span>
  )
}

function PointsDelta({ value }: { value: number | null | undefined }) {
  if (value == null) {
    return <EmptyRunCell />
  }

  return (
    <span
      className={cn(
        "block text-center font-mono font-medium tabular-nums",
        value < 0
          ? "text-emerald-600 dark:text-emerald-400"
          : value > 0
            ? "text-red-600 dark:text-red-400"
            : "text-muted-foreground",
      )}
    >
      {`${value < 0 ? "-" : "+"}${formatMetric(Math.abs(value))}`}
    </span>
  )
}

function CompareRunsTable({
  rows,
  player1Name,
  player2Name,
  onlyBoth,
}: {
  rows: PlayerCompareRunPublic[]
  player1Name: string
  player2Name: string
  onlyBoth: boolean
}) {
  const { t } = useTranslation()
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const loadMoreRef = useRef<HTMLDivElement | null>(null)
  const sortedRows = useMemo(() => {
    const filtered = onlyBoth
      ? rows.filter((row) => row.player1 != null && row.player2 != null)
      : rows
    return [...filtered].sort((left, right) => {
      const leftPoints = left.player1?.points ?? -1
      const rightPoints = right.player1?.points ?? -1
      if (leftPoints !== rightPoints) {
        return rightPoints - leftPoints
      }
      return left.map_name.localeCompare(right.map_name, undefined, {
        numeric: true,
        sensitivity: "base",
      })
    })
  }, [onlyBoth, rows])
  const visibleRows = sortedRows.slice(0, visibleCount)

  useEffect(() => {
    if (visibleCount > sortedRows.length) {
      setVisibleCount(PAGE_SIZE)
    }
  }, [sortedRows.length, visibleCount])

  useEffect(() => {
    const target = loadMoreRef.current
    if (!target || visibleCount >= sortedRows.length) {
      return
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) {
          return
        }
        startTransition(() => {
          setVisibleCount((current) =>
            Math.min(current + PAGE_SIZE, sortedRows.length),
          )
        })
      },
      { rootMargin: "320px 0px" },
    )
    observer.observe(target)
    return () => observer.disconnect()
  }, [sortedRows.length, visibleCount])

  return (
    <section className="space-y-3">
      {sortedRows.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          {t("compare.noRuns")}
        </p>
      ) : (
        <>
          <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm">
            <div className="overflow-x-auto">
              <Table className="min-w-[1220px]">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="min-w-60 normal-case tracking-normal text-foreground/80">
                      {t("labels.map")}
                    </TableHead>
                    <TableHead className="min-w-14 normal-case tracking-normal text-foreground/80">
                      {t("labels.tier")}
                    </TableHead>
                    <TableHead className="min-w-14 normal-case tracking-normal text-foreground/80">
                      {t("labels.mode")}
                    </TableHead>
                    <TableHead className="min-w-14 normal-case tracking-normal text-foreground/80">
                      {t("labels.tps")}
                    </TableHead>
                    <TableHead className="min-w-24 text-right normal-case tracking-normal text-foreground/80">
                      {player1Name}
                    </TableHead>
                    <TableHead className="min-w-24 text-right normal-case tracking-normal text-foreground/80">
                      {t("compare.timeDelta")}
                    </TableHead>
                    <TableHead className="min-w-24 normal-case tracking-normal text-foreground/80">
                      {t("labels.points")}
                    </TableHead>
                    <TableHead className="min-w-24 text-center normal-case tracking-normal text-foreground/80">
                      {t("compare.pointsDelta")}
                    </TableHead>
                    <TableHead className="min-w-14 normal-case tracking-normal text-foreground/80">
                      {t("labels.mode")}
                    </TableHead>
                    <TableHead className="min-w-14 normal-case tracking-normal text-foreground/80">
                      {t("labels.tps")}
                    </TableHead>
                    <TableHead className="min-w-24 text-right normal-case tracking-normal text-foreground/80">
                      {player2Name}
                    </TableHead>
                    <TableHead className="min-w-24 normal-case tracking-normal text-foreground/80">
                      {t("labels.points")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleRows.map((row) => {
                    const player1Record = row.player1 ?? null
                    const player2Record = row.player2 ?? null
                    const primaryRecord = player1Record ?? player2Record

                    return (
                      <TableRow key={row.map_id}>
                        <TableCell>
                          <MapDisplay
                            mapName={row.map_name}
                            mapId={row.map_id}
                            imageUrls={getMapImageUrls(
                              row.map_name,
                              primaryRecord?.workshop_id,
                            )}
                          />
                        </TableCell>
                        <TableCell>
                          <TierBadge tier={row.map_tier} hideWhenUnknown />
                        </TableCell>
                        <TableCell>
                          {player1Record ? (
                            <ModeBadge mode={player1Record.mode} />
                          ) : (
                            <EmptyRunCell />
                          )}
                        </TableCell>
                        <TableCell>
                          {player1Record ? (
                            <TeleportsBadge
                              teleports={player1Record.teleports}
                            />
                          ) : (
                            <EmptyRunCell />
                          )}
                        </TableCell>
                        <TableCell className="text-right font-mono font-medium tabular-nums">
                          {player1Record ? (
                            formatRecordTime(player1Record.time)
                          ) : (
                            <EmptyRunCell />
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <TimeDelta value={row.time_delta} />
                        </TableCell>
                        <TableCell>
                          {player1Record ? (
                            <PointsBadge points={player1Record.points} />
                          ) : (
                            <EmptyRunCell />
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          <PointsDelta value={row.points_delta} />
                        </TableCell>
                        <TableCell>
                          {player2Record ? (
                            <ModeBadge mode={player2Record.mode} />
                          ) : (
                            <EmptyRunCell />
                          )}
                        </TableCell>
                        <TableCell>
                          {player2Record ? (
                            <TeleportsBadge
                              teleports={player2Record.teleports}
                            />
                          ) : (
                            <EmptyRunCell />
                          )}
                        </TableCell>
                        <TableCell className="text-right font-mono font-medium tabular-nums">
                          {player2Record ? (
                            formatRecordTime(player2Record.time)
                          ) : (
                            <EmptyRunCell />
                          )}
                        </TableCell>
                        <TableCell>
                          {player2Record ? (
                            <PointsBadge points={player2Record.points} />
                          ) : (
                            <EmptyRunCell />
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          </div>
          {visibleCount < sortedRows.length ? (
            <div
              ref={loadMoreRef}
              className="flex h-12 items-center justify-center"
            >
              <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
            </div>
          ) : null}
        </>
      )}
    </section>
  )
}

type ComparisonMetric = {
  label: string
  player1Value: number | null | undefined
  player2Value: number | null | undefined
  formatValue: (value: number) => string
  higherIsBetter?: boolean
}

function MetricDifferenceBadge({
  value,
  higherIsBetter,
}: {
  value: number
  higherIsBetter: boolean
}) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "shrink-0 font-mono text-[10px] tabular-nums",
        higherIsBetter
          ? "border-emerald-300/70 bg-emerald-100 text-emerald-900 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-200"
          : "border-red-300/70 bg-red-100 text-red-900 dark:border-red-500/40 dark:bg-red-500/15 dark:text-red-200",
      )}
    >
      +{formatMetric(value)}
    </Badge>
  )
}

function MetricRow({
  label,
  player1Value,
  player2Value,
  formatValue,
  higherIsBetter = true,
}: ComparisonMetric) {
  const difference =
    player1Value != null && player2Value != null
      ? Math.abs(player1Value - player2Value)
      : null
  const showDifference = difference != null && difference > 0
  const player1HasLargerValue =
    showDifference && player1Value != null && player2Value != null
      ? player1Value > player2Value
      : false

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 py-3">
      <div className="flex min-w-0 items-center justify-end gap-1.5">
        {player1HasLargerValue && difference != null ? (
          <MetricDifferenceBadge
            value={difference}
            higherIsBetter={higherIsBetter}
          />
        ) : null}
        <span className="truncate font-mono text-sm font-semibold tabular-nums">
          {player1Value == null ? "-" : formatValue(player1Value)}
        </span>
      </div>
      <span className="min-w-28 text-center text-xs font-medium text-muted-foreground">
        {label}
      </span>
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="truncate font-mono text-sm font-semibold tabular-nums">
          {player2Value == null ? "-" : formatValue(player2Value)}
        </span>
        {showDifference && !player1HasLargerValue && difference != null ? (
          <MetricDifferenceBadge
            value={difference}
            higherIsBetter={higherIsBetter}
          />
        ) : null}
      </div>
    </div>
  )
}

function ComparePlayerIdentity({
  player,
  name,
  align,
}: {
  player: GraphqlPlayer | null
  name: string
  align: "left" | "right"
}) {
  const avatarSrc = player?.avatarHash
    ? `https://avatars.steamstatic.com/${player.avatarHash}_full.jpg`
    : undefined
  const highestPermission = getHighestPlayerPermission(player?.roles)
  const showRoleRing = highestPermission !== null

  return (
    <div
      className={cn(
        "flex min-w-0 items-center gap-3 p-3 sm:p-4",
        align === "right" ? "flex-row-reverse text-right" : "text-left",
      )}
    >
      <Avatar
        className={cn(
          "size-16 shrink-0 rounded-2xl border border-border/60 sm:size-20 sm:rounded-[22px]",
          showRoleRing && "ring-4 ring-offset-4 ring-offset-card",
          highestPermission &&
            PLAYER_PERMISSION_RING_CLASS_NAMES[highestPermission],
        )}
      >
        <AvatarImage
          className="object-cover"
          src={avatarSrc}
          alt={`${name} avatar`}
        />
        <AvatarFallback className="rounded-2xl bg-primary text-lg font-semibold text-primary-foreground sm:rounded-[22px]">
          {getInitials(name)}
        </AvatarFallback>
      </Avatar>
      <div className={cn("min-w-0", align === "right" && "items-end")}>
        <div
          className={cn(
            "flex min-w-0 items-center gap-2",
            align === "right" && "justify-end",
          )}
        >
          <CountryFlag
            countryCode={player?.country}
            className="h-5 w-7 rounded-[4px]"
            fallbackClassName="h-5 w-7 rounded-[4px]"
          />
          <h2 className="truncate text-lg font-semibold sm:text-xl">{name}</h2>
        </div>
      </div>
    </div>
  )
}

export function ComparePage({
  initialPlayer1,
  initialPlayer2,
}: {
  initialPlayer1?: string
  initialPlayer2?: string
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { scope } = useScope()
  const [runType, setRunType] = useState<"NUB" | "PRO">("NUB")
  const [onlyBoth, setOnlyBoth] = useState(true)
  const [selectionError, setSelectionError] = useState<string | null>(null)
  const player1Query = useQuery({
    queryKey: ["compare-player", initialPlayer1],
    queryFn: () => fetchPlayerByIdentifier(initialPlayer1 ?? ""),
    enabled: Boolean(initialPlayer1),
    retry: false,
  })
  const player2Query = useQuery({
    queryKey: ["compare-player", initialPlayer2],
    queryFn: () => fetchPlayerByIdentifier(initialPlayer2 ?? ""),
    enabled: Boolean(initialPlayer2),
    retry: false,
  })
  const comparisonQuery = useQuery({
    queryKey: ["player-comparison", initialPlayer1, initialPlayer2, scope],
    queryFn: () =>
      fetchComparison({
        player1: initialPlayer1 ?? "",
        player2: initialPlayer2 ?? "",
        scope,
      }),
    enabled: Boolean(initialPlayer1 && initialPlayer2),
    retry: false,
  })
  const player1 = player1Query.data ?? null
  const player2 = player2Query.data ?? null
  const comparison = comparisonQuery.data
  const player1Name =
    comparison?.player1.player.display_name ??
    player1?.displayName ??
    t("compare.player1")
  const player2Name =
    comparison?.player2.player.display_name ??
    player2?.displayName ??
    t("compare.player2")

  const setPlayer = (slot: "player1" | "player2", player: GraphqlPlayer) => {
    const otherPlayer = slot === "player1" ? initialPlayer2 : initialPlayer1
    if (player.steamid64 === otherPlayer) {
      setSelectionError(t("compare.duplicatePlayers"))
      return
    }
    setSelectionError(null)
    void navigate({
      to: "/compare",
      search: (previous) => ({ ...previous, [slot]: player.steamid64 }),
    })
  }

  const clearPlayer = (slot: "player1" | "player2") => {
    setSelectionError(null)
    void navigate({
      to: "/compare",
      search: (previous) => ({ ...previous, [slot]: undefined }),
    })
  }

  const swapPlayers = () => {
    setSelectionError(null)
    void navigate({
      to: "/compare",
      search: (previous) => ({
        ...previous,
        player1: initialPlayer2,
        player2: initialPlayer1,
      }),
    })
  }

  const metrics: ComparisonMetric[] = comparison
    ? [
        {
          label: t("labels.rating"),
          player1Value: comparison.player1.rating,
          player2Value: comparison.player2.rating,
          formatValue: formatRating,
        },
        {
          label: t("compare.globalRank"),
          player1Value: comparison.player1.global_rank,
          player2Value: comparison.player2.global_rank,
          formatValue: formatMetric,
          higherIsBetter: false,
        },
        {
          label: t("labels.points"),
          player1Value: comparison.player1.points,
          player2Value: comparison.player2.points,
          formatValue: formatMetric,
        },
        {
          label: t("compare.ratingEasy"),
          player1Value: comparison.player1.rating_easy,
          player2Value: comparison.player2.rating_easy,
          formatValue: formatRating,
        },
        {
          label: t("compare.ratingHard"),
          player1Value: comparison.player1.rating_hard,
          player2Value: comparison.player2.rating_hard,
          formatValue: formatRating,
        },
        {
          label: t("compare.nubWrs"),
          player1Value: comparison.player1.wrs_nub,
          player2Value: comparison.player2.wrs_nub,
          formatValue: formatMetric,
        },
        {
          label: t("compare.proWrs"),
          player1Value: comparison.player1.wrs_pro,
          player2Value: comparison.player2.wrs_pro,
          formatValue: formatMetric,
        },
        {
          label: t("compare.records900"),
          player1Value: comparison.player1.records_900_plus,
          player2Value: comparison.player2.records_900_plus,
          formatValue: formatMetric,
        },
        {
          label: t("compare.records800"),
          player1Value: comparison.player1.records_800_plus,
          player2Value: comparison.player2.records_800_plus,
          formatValue: formatMetric,
        },
      ]
    : []

  const playerSelection = (
    <section className="grid items-end gap-3 xl:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
      <PlayerSearchSelect
        ariaLabel={t("compare.player1Search")}
        clearOnSelect
        clearButtonLabel={t("compare.clearPlayer1")}
        label={t("compare.player1")}
        searchQueryKey="compare-player1"
        showSelectedPlayerDisplay={false}
        selectedPlayer={player1}
        onClearPlayer={() => clearPlayer("player1")}
        onSelectPlayer={(player) => setPlayer("player1", player)}
      />
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="mb-0.5"
        aria-label={t("compare.swapPlayers")}
        disabled={!initialPlayer1 || !initialPlayer2}
        onClick={swapPlayers}
      >
        <ArrowLeftRight />
      </Button>
      <PlayerSearchSelect
        ariaLabel={t("compare.player2Search")}
        clearOnSelect
        clearButtonLabel={t("compare.clearPlayer2")}
        label={t("compare.player2")}
        searchQueryKey="compare-player2"
        showSelectedPlayerDisplay={false}
        selectedPlayer={player2}
        onClearPlayer={() => clearPlayer("player2")}
        onSelectPlayer={(player) => setPlayer("player2", player)}
      />
    </section>
  )

  return (
    <main className="space-y-8 pb-10">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold">{t("compare.title")}</h1>
      </div>
      {!initialPlayer1 || !initialPlayer2 ? (
        <>
          {playerSelection}
          {selectionError ? (
            <p className="text-sm text-destructive">{selectionError}</p>
          ) : null}
          <p className="border-y py-12 text-center text-sm text-muted-foreground">
            {t("compare.selectBoth")}
          </p>
        </>
      ) : comparisonQuery.isLoading ? (
        <>
          {playerSelection}
          <div className="flex min-h-72 items-center justify-center text-sm text-muted-foreground">
            <LoaderCircle className="mr-2 size-4 animate-spin" />
            {t("compare.loading")}
          </div>
        </>
      ) : comparisonQuery.isError || !comparison ? (
        <>
          {playerSelection}
          <p className="border-y py-12 text-center text-sm text-destructive">
            {t("compare.loadFailed")}
          </p>
        </>
      ) : (
        <>
          <section className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(20rem,0.85fr)]">
            <Card className="min-w-0 border-border/70 bg-card/95 py-0">
              <CardContent className="space-y-6 p-5 sm:p-6">
                {playerSelection}
                {selectionError ? (
                  <p className="text-sm text-destructive">{selectionError}</p>
                ) : null}
                <section className="pt-5">
                  <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 pb-3">
                    <ComparePlayerIdentity
                      player={player1}
                      name={player1Name}
                      align="right"
                    />
                    <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      VS
                    </span>
                    <ComparePlayerIdentity
                      player={player2}
                      name={player2Name}
                      align="left"
                    />
                  </div>
                  <span className="block py-1 text-center text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    {scope}
                  </span>
                  {metrics.map((metric) => (
                    <MetricRow key={metric.label} {...metric} />
                  ))}
                </section>
              </CardContent>
            </Card>
            <Card className="min-w-0 border-border/70 bg-card/95 py-0">
              <CardContent className="space-y-4 p-5 sm:p-6">
                <h2 className="text-lg font-semibold">
                  {t("compare.progression")}
                </h2>
                <ComparisonRadar
                  comparison={comparison}
                  player1Name={player1Name}
                  player2Name={player2Name}
                />
              </CardContent>
            </Card>
          </section>
          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold">{t("compare.runs")}</h2>
              <div className="flex flex-wrap items-center gap-2">
                <Label
                  htmlFor="compare-runs-pro-only"
                  className="flex h-9 w-fit items-center justify-start gap-2 rounded-lg border border-border/70 bg-background/80 px-3 text-[11px] font-medium tracking-[0.08em] text-foreground/80 uppercase"
                >
                  <Switch
                    id="compare-runs-pro-only"
                    checked={runType === "PRO"}
                    onCheckedChange={(checked) =>
                      setRunType(checked ? "PRO" : "NUB")
                    }
                    className="data-[state=unchecked]:bg-[#f3c40f] data-[state=unchecked]:shadow-[#f3c40f]/35 data-[state=checked]:bg-[#3598db] data-[state=checked]:shadow-[#3598db]/35 dark:data-[state=checked]:bg-[#3598db]"
                  />
                  <span>{runType}</span>
                </Label>
                <Label
                  htmlFor="compare-runs-only-both"
                  className="flex h-9 w-fit items-center justify-start gap-2 rounded-lg border border-border/70 bg-background/80 px-3 text-[11px] font-medium tracking-[0.08em] text-foreground/80"
                >
                  <Switch
                    id="compare-runs-only-both"
                    checked={onlyBoth}
                    onCheckedChange={setOnlyBoth}
                  />
                  <span>{t("compare.onlyBoth")}</span>
                </Label>
              </div>
            </div>
            <CompareRunsTable
              rows={
                runType === "NUB" ? comparison.nub_runs : comparison.pro_runs
              }
              player1Name={player1Name}
              player2Name={player2Name}
              onlyBoth={onlyBoth}
            />
          </section>
        </>
      )}
    </main>
  )
}
