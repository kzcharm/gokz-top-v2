import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import type { EChartsOption, EChartsType } from "echarts"
import * as echarts from "echarts"
import { ArrowLeftRight, LoaderCircle } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import type { PlayerComparisonPublic } from "@/client"

import { PlayersService } from "@/client"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { PlayerSearchSelect } from "@/components/Common/PlayerSearchSelect"
import {
  formatRating,
  getProfilePointsStandingQueryOptions,
  type ProfileSkillKey,
  type ProfileSkillRatings,
} from "@/components/Profile/profile-utils"
import { useScope } from "@/components/scope-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  fetchPlayerByIdentifier,
  type GraphqlPlayer,
} from "@/lib/player-graphql"
import { cn } from "@/lib/utils"
import { CompareCompletion } from "./CompareCompletion"
import { CompareRunsTable } from "./CompareRunsTable"

const SKILLS: ProfileSkillKey[] = [
  "boxtech",
  "strafe",
  "bhop",
  "climb",
  "ladder",
  "slide",
]

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

function ComparisonRadar({
  ratings1,
  ratings2,
  player1Name,
  player2Name,
}: {
  ratings1: ProfileSkillRatings | null
  ratings2: ProfileSkillRatings | null
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
    const values = SKILLS
    const option: EChartsOption = {
      color: ["#0f9d8b", "#e8792f"],
      legend: { bottom: 0, data: [player1Name, player2Name] },
      radar: {
        startAngle: 90,
        radius: "62%",
        center: ["50%", "46%"],
        indicator: values.map((skill) => ({
          name: t(`profile.skillRadar.${skill}`),
          max: 11,
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
            { name: player1Name, ratings: ratings1, color: "#0f9d8b" },
            { name: player2Name, ratings: ratings2, color: "#e8792f" },
          ]
            .filter(
              ({ ratings }) =>
                ratings &&
                SKILLS.every((skill) => ratings[skill]?.rating != null),
            )
            .map(({ name, ratings, color }) => ({
              itemStyle: { color },
              lineStyle: { color },
              name,
              value: SKILLS.map((skill) => ratings?.[skill]?.rating ?? 0),
              areaStyle: { opacity: 0.14 },
            })),
        },
      ],
      tooltip: {
        formatter: (params) => {
          const item = Array.isArray(params) ? params[0] : params
          const values = Array.isArray(item.value) ? item.value : []
          return values
            .map(
              (value, index) =>
                `${t(`profile.skillRadar.${SKILLS[index]}`)}: ${formatRating(Number(value))}`,
            )
            .join("<br />")
        },
      },
    }
    chart.setOption(option, true)
  }, [ratings1, ratings2, player1Name, player2Name, t])

  return (
    <div
      ref={chartElementRef}
      className="h-64 w-full"
      role="img"
      aria-label={t("compare.skillsAria", {
        player1: player1Name,
        player2: player2Name,
      })}
    />
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
    <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 rounded-lg bg-muted/30 px-2 py-2">
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
      <span className="min-w-16 text-center text-xs font-medium text-muted-foreground">
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
  const skills1 = useQuery(
    getProfilePointsStandingQueryOptions({
      identifier: initialPlayer1 ?? null,
      scope,
    }),
  )
  const skills2 = useQuery(
    getProfilePointsStandingQueryOptions({
      identifier: initialPlayer2 ?? null,
      scope,
    }),
  )
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
          <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem] xl:items-start">
            <Card className="min-w-0 border-border/70 bg-card/95 py-0">
              <CardContent className="space-y-6 p-5 sm:p-6">
                {playerSelection}
                {selectionError ? (
                  <p className="text-sm text-destructive">{selectionError}</p>
                ) : null}
                <section className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-2">
                    {(["player1", "player2"] as const).map((slot, index) => (
                      <div key={slot} className="min-w-0 space-y-4">
                        <div
                          className={cn(
                            "border-l-4 pl-3",
                            index === 0
                              ? "border-[#0f9d8b]"
                              : "border-[#e8792f]",
                          )}
                        >
                          <PlayerDisplay
                            player={
                              (index === 0 ? player1 : player2) ??
                              comparison[slot].player
                            }
                          />
                        </div>
                        <CompareCompletion
                          comparison={comparison}
                          slot={slot}
                        />
                      </div>
                    ))}
                  </div>
                </section>
              </CardContent>
            </Card>
            <Card className="min-w-0 border-border/70 bg-card/95 py-0">
              <CardContent className="space-y-4 p-5 sm:p-6">
                <h2 className="text-lg font-semibold">
                  {t("profile.skillRadar.title")}
                </h2>
                <p className="text-xs text-muted-foreground">
                  {t("profile.skillRadar.globalHint")}
                </p>
                <ComparisonRadar
                  ratings1={skills1.data?.skillRatings ?? null}
                  ratings2={skills2.data?.skillRatings ?? null}
                  player1Name={player1Name}
                  player2Name={player2Name}
                />
                {skills1.isError ||
                skills2.isError ||
                skills1.isLoading ||
                skills2.isLoading ||
                !skills1.data?.skillRatings ||
                !skills2.data?.skillRatings ? (
                  <p className="text-xs text-muted-foreground">
                    {skills1.isError || skills2.isError
                      ? t("compare.loadFailed")
                      : skills1.isLoading || skills2.isLoading
                        ? t("compare.loading")
                        : t("compare.skillsMissing")}
                  </p>
                ) : null}
                <p className="text-center text-xs text-muted-foreground">
                  {scope}
                </p>
                <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-1">
                  {metrics.map((metric) => (
                    <MetricRow key={metric.label} {...metric} />
                  ))}
                </div>
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
