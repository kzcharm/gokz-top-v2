import { useQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { LeaderboardsService, type MapPublic, MapsService } from "@/client"
import { formatRecordTime } from "@/components/Records/utils"
import { formatWrGap, getWrGap } from "@/components/Records/wr-gap"
import type { AppScope } from "@/components/scope-provider"
import { Skeleton } from "@/components/ui/skeleton"
import { formatNumber } from "@/i18n/locale"
import type { MapMetric } from "./catalog-metrics"
import { MapMetricTooltip } from "./MapMetricTooltip"

export function MapOverviewMetrics({
  map,
  scope,
}: {
  map: MapPublic
  scope: AppScope
}) {
  const { t } = useTranslation()
  const enabled = map.validated && map.id > 0
  const metricsQuery = useQuery({
    queryKey: ["map", "metrics", map.id, scope],
    queryFn: () =>
      LeaderboardsService.readMapLeaderboard({ mapId: map.id, scope }),
    enabled,
    staleTime: 30_000,
    retry: false,
  })
  // Share the main-course NUB WR request with the records view when possible.
  const nubWrQuery = useQuery({
    queryKey: ["map", "wrs", map.id, scope, false],
    queryFn: () =>
      MapsService.readMapWrs({ mapId: map.id, scope, type: "NUB" }),
    enabled,
    staleTime: 30_000,
    retry: false,
  })
  const entry = metricsQuery.isError
    ? undefined
    : metricsQuery.data?.data.find((item) => item.map.id === map.id)
  const available = entry?.updated_at != null
  const hasFinishers = available && entry.unique_nub_finishes > 0
  const gap =
    hasFinishers && !nubWrQuery.isError
      ? getWrGap(
          entry.median_first_completion_time,
          nubWrQuery.data?.[0]?.time ?? Number.NaN,
        )
      : null
  const firstFinishGap =
    hasFinishers &&
    entry.median_first_finish_time != null &&
    !nubWrQuery.isError
      ? getWrGap(
          entry.median_first_finish_time,
          nubWrQuery.data?.[0]?.time ?? Number.NaN,
        )
      : null
  const time = available ? entry.total_playtime : null
  const formatDuration = (seconds: number) =>
    seconds >= 3600
      ? t("maps.overview.hours", {
          value: formatNumber(seconds / 3600, { maximumFractionDigits: 1 }),
        })
      : formatRecordTime(Math.round(seconds)).replace(/\.000$/, "")
  const metrics: {
    key: MapMetric | "avgFinishes" | "firstFinishMed" | "firstFinishMedWrGap"
    label: string
    value: string
    loading?: boolean
  }[] = [
    {
      key: "finishes",
      label: t("maps.sortOptions.finishes"),
      value: available ? formatNumber(entry.total_finishes) : "—",
    },
    {
      key: "playtime",
      label: t("maps.overview.recordedRunTime"),
      value: time == null ? "—" : formatDuration(time),
    },
    {
      key: "avgFinishes",
      label: t("maps.overview.avgFinishes"),
      value: hasFinishers
        ? formatNumber(entry.average_finishes_per_player, {
            maximumFractionDigits: 2,
          })
        : "—",
    },
    {
      key: "avgPlaytime",
      label: t("maps.overview.avgPlaytime"),
      value: hasFinishers
        ? formatDuration(entry.average_playtime_per_player)
        : "—",
    },
    {
      key: "nub",
      label: t("maps.sortOptions.nub"),
      value: available ? formatNumber(entry.unique_nub_finishes) : "—",
    },
    {
      key: "pro",
      label: t("maps.sortOptions.pro"),
      value: available ? formatNumber(entry.unique_pro_finishes) : "—",
    },
    {
      key: "proRatio",
      label: t("maps.overview.proShare"),
      value: hasFinishers
        ? `${formatNumber(entry.pro_nub_ratio * 100, { maximumFractionDigits: 1 })}%`
        : "—",
    },
    {
      key: "firstMed",
      label: t("maps.overview.medianPbTime"),
      value:
        hasFinishers && entry.median_first_completion_time > 0
          ? formatRecordTime(
              Math.round(entry.median_first_completion_time),
            ).replace(/\.000$/, "")
          : "—",
    },
    {
      key: "firstMedWrGap",
      label: t("maps.overview.medianPbWrGap"),
      value: gap == null ? "—" : formatWrGap(gap),
      loading: metricsQuery.isLoading || (hasFinishers && nubWrQuery.isLoading),
    },
    {
      key: "firstFinishMed",
      label: t("maps.overview.medianFirstFinishTime"),
      value:
        hasFinishers &&
        entry.median_first_finish_time != null &&
        entry.median_first_finish_time > 0
          ? formatRecordTime(
              Math.round(entry.median_first_finish_time),
            ).replace(/\.000$/, "")
          : "—",
    },
    {
      key: "firstFinishMedWrGap",
      label: t("maps.overview.medianFirstFinishWrGap"),
      value: firstFinishGap == null ? "—" : formatWrGap(firstFinishGap),
      loading: metricsQuery.isLoading || (hasFinishers && nubWrQuery.isLoading),
    },
    {
      key: "bonus",
      label: t("maps.overview.bonuses"),
      value: formatNumber(map.bonus_count ?? 0),
      loading: false,
    },
  ]
  return (
    <section
      className="flex min-w-0 flex-col gap-4 px-6 py-5 sm:px-8"
      aria-label={t("maps.overview.metrics")}
      aria-busy={metricsQuery.isLoading}
    >
      {!available && !metricsQuery.isLoading ? (
        <p className="text-xs text-muted-foreground">
          {t("maps.overview.metricsUnavailable")}
        </p>
      ) : null}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-3 xl:grid-cols-6">
        {metrics.map((metric) => (
          <div key={metric.key} className="flex min-w-0 flex-col gap-1">
            <dt className="text-xs text-muted-foreground">
              <MapMetricTooltip
                label={metric.label}
                explanation={t(`maps.metricHelp.${metric.key}`)}
              >
                <button
                  type="button"
                  className="min-w-0 rounded-sm text-left focus-visible:outline-2 focus-visible:outline-ring"
                >
                  {metric.label}
                </button>
              </MapMetricTooltip>
            </dt>
            <dd className="text-base font-semibold tabular-nums">
              {(metric.loading ?? metricsQuery.isLoading) ? (
                <Skeleton className="h-6 w-16" />
              ) : (
                metric.value
              )}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
