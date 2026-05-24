import type { EChartsOption } from "echarts"
import * as echarts from "echarts"
import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"

import type {
  MapStatsPublic,
  MapWrGapDistributionContentPublic,
} from "@/client"
import { useTheme } from "@/components/theme-provider"
import { Card, CardContent } from "@/components/ui/card"
import { useMediaQuery } from "@/hooks/useMobile"

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function formatMedianWrGap(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) {
    return null
  }
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
  }).format(value)
}

function medianWrGapToRecordTime(
  wrTime: number | null | undefined,
  medianWrGap: number | null | undefined,
) {
  return wrGapBoundToRecordTime(wrTime, medianWrGap)
}

function formatChartTimeSeconds(value: number) {
  if (!Number.isFinite(value) || value < 0) {
    return "--:--"
  }

  const roundedSeconds = Math.round(value)
  if (roundedSeconds >= 3600) {
    const hours = roundedSeconds / 3600
    return `${new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 1,
    }).format(hours).replace(/\.0$/, "")} h`
  }

  const minutes = Math.floor(roundedSeconds / 60)
  const seconds = roundedSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, "0")}`
}

function formatBucketPercent(count: number, total: number) {
  if (total <= 0) {
    return "0%"
  }
  const percent = (count / total) * 100
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(percent).replace(/\.0$/, "") + "%"
}

function wrGapBoundToRecordTime(
  wrTime: number | null | undefined,
  wrGapBound: number | null | undefined,
) {
  if (
    wrTime == null ||
    !Number.isFinite(wrTime) ||
    wrTime <= 0 ||
    wrGapBound == null ||
    !Number.isFinite(wrGapBound)
  ) {
    return null
  }

  return wrTime * (1 + 2 ** wrGapBound)
}

function recordTimeToWrGap(
  wrTime: number | null | undefined,
  recordTime: number | null | undefined,
) {
  if (
    wrTime == null ||
    !Number.isFinite(wrTime) ||
    wrTime <= 0 ||
    recordTime == null ||
    !Number.isFinite(recordTime) ||
    recordTime <= wrTime
  ) {
    return null
  }

  const ratioDelta = recordTime / wrTime - 1
  if (!Number.isFinite(ratioDelta) || ratioDelta <= 0) {
    return null
  }

  const wrGap = Math.log2(ratioDelta)
  return Number.isFinite(wrGap) ? wrGap : null
}

function formatWrGapAxisLabel(value: number) {
  if (Math.abs(value) < 1e-9) {
    return "0"
  }
  if (Math.abs(value - Math.round(value)) < 1e-9) {
    return `${Math.round(value)}`
  }
  return value.toFixed(1)
}

function roundDownToBinStart(value: number) {
  return Math.floor(value / 0.5) * 0.5
}

function valueToPlotX({
  value,
  plotLeft,
  plotWidth,
  axisMin,
  axisMax,
}: {
  value: number
  plotLeft: number
  plotWidth: number
  axisMin: number
  axisMax: number
}) {
  const axisSpan = Math.max(axisMax - axisMin, 0.5)
  return plotLeft + ((axisMax - value) / axisSpan) * plotWidth
}

function WrGapDistributionChart({
  distribution,
  title,
  testId,
  playerRecordTime,
  showPlayerMarker,
}: {
  distribution: MapWrGapDistributionContentPublic
  title: string
  testId: string
  playerRecordTime: number | null
  showPlayerMarker: boolean
}) {
  const { t } = useTranslation()
  const chartRef = useRef<HTMLDivElement | null>(null)
  const { resolvedTheme } = useTheme()
  const isNarrowViewport = useMediaQuery("(max-width: 1279px)")
  const bins = distribution.bins ?? []
  const playerWrGap = recordTimeToWrGap(distribution.wr_time, playerRecordTime)
  const medianWrGap = distribution.median_wr_gap
  const medianStart =
    medianWrGap == null ||
    !Number.isFinite(medianWrGap)
      ? (bins[0]?.lower_bound ?? 0)
      : roundDownToBinStart(medianWrGap)
  const xAxisMin = medianStart - 6
  const xAxisMax = medianStart + 0.5 + 6
  const visibleBins = bins.filter((bin) => {
    const lowerBound = bin.lower_bound ?? 0
    const upperBound = bin.upper_bound ?? lowerBound + 0.5
    return lowerBound >= xAxisMin - 1e-9 && upperBound <= xAxisMax + 1e-9
  })
  const barData = visibleBins.map((bin) => [
    ((bin.lower_bound ?? 0) + (bin.upper_bound ?? 0)) / 2,
    bin.count ?? 0,
  ])

  useEffect(() => {
    const element = chartRef.current
    if (!element || visibleBins.length === 0) {
      return
    }

    const chart = echarts.init(element)
    const axisColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.72)"
        : "rgba(15, 23, 42, 0.58)"
    const splitLineColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.08)"
        : "rgba(15, 23, 42, 0.08)"
    const markerColor =
      resolvedTheme === "dark" ? "rgba(248, 113, 113, 0.95)" : "rgba(220, 38, 38, 0.95)"
    const markerTextColor = resolvedTheme === "dark" ? "#fecaca" : "#991b1b"
    const barColor =
      resolvedTheme === "dark"
        ? "oklch(0.5106 0.2301 276.9656)"
        : "oklch(0.5854 0.2041 277.1173)"
    const barHoverColor =
      resolvedTheme === "dark"
        ? "oklch(0.4568 0.2146 277.0229)"
        : "oklch(0.5106 0.2301 276.9656)"
    const barStyle = {
      color: barColor,
      borderRadius: [6, 6, 0, 0] as [number, number, number, number],
      opacity: 1,
    }
    const barHoverStyle = {
      ...barStyle,
      color: barHoverColor,
    }
    const chartTop = 24
    const chartBottom = 112
    const chartLeft = 44
    const chartRight = 16
    const buildOption = (): EChartsOption => {
      const plotLeft = chartLeft
      const plotRight = Math.max(element.clientWidth - chartRight, chartLeft)
      const plotWidth = Math.max(plotRight - plotLeft, 0)
      const leftEdge = xAxisMin
      const rightEdge = xAxisMax
      const graphics: NonNullable<EChartsOption["graphic"]> = []

      if (medianWrGap != null && Number.isFinite(medianWrGap)) {
        const medianX = valueToPlotX({
          value: medianWrGap,
          plotLeft,
          plotWidth,
          axisMin: leftEdge,
          axisMax: rightEdge,
        })
        const clampedMedianX = Math.min(
          Math.max(medianX, plotLeft),
          plotRight,
        )
        graphics.push({
          type: "line",
          silent: true,
          shape: {
            x1: clampedMedianX,
            y1: chartTop,
            x2: clampedMedianX,
            y2: Math.max(element.clientHeight - chartBottom, chartTop),
          },
          style: {
            stroke:
              resolvedTheme === "dark"
                ? "rgba(34, 197, 94, 0.95)"
                : "rgba(22, 163, 74, 0.95)",
            lineWidth: 2,
            lineDash: [4, 4],
          },
        })
        graphics.push({
          type: "text",
          silent: true,
          style: {
            x: Math.min(clampedMedianX + 6, plotRight - 40),
            y: 4,
            text: t("maps.stats.medianMarker"),
            fill:
              resolvedTheme === "dark" ? "#86efac" : "#166534",
            fontSize: 11,
            fontWeight: 600,
          },
        })
      }

      if (showPlayerMarker && playerWrGap != null) {
        const playerX = valueToPlotX({
          value: playerWrGap,
          plotLeft,
          plotWidth,
          axisMin: leftEdge,
          axisMax: rightEdge,
        })
        const clampedPlayerX = Math.min(Math.max(playerX, plotLeft), plotRight)

        graphics.push({
          type: "line",
          silent: true,
          shape: {
            x1: clampedPlayerX,
            y1: chartTop,
            x2: clampedPlayerX,
            y2: Math.max(element.clientHeight - chartBottom, chartTop),
          },
          style: {
            stroke: markerColor,
            lineWidth: 2,
            lineDash: [6, 4],
          },
        })
        graphics.push({
          type: "text",
          silent: true,
          style: {
            x: Math.min(clampedPlayerX + 6, plotRight - 24),
            y: 4,
            text: t("maps.stats.youMarker"),
            fill: markerTextColor,
            fontSize: 11,
            fontWeight: 600,
          },
        })
      }

      return {
        animationDuration: 250,
        animationDurationUpdate: 180,
        grid: {
          top: chartTop,
          right: chartRight,
          bottom: chartBottom,
          left: chartLeft,
        },
        tooltip: {
          trigger: "item",
          formatter: (params) => {
            const entry = Array.isArray(params) ? params[0] : params
            if (!entry) {
              return ""
            }
            const dataIndex =
              typeof entry.dataIndex === "number" ? entry.dataIndex : -1
            const bin = dataIndex >= 0 ? visibleBins[dataIndex] : undefined
            const value =
              Array.isArray(entry.value) ? Number(entry.value[1]) : Number(entry.value)
            const lowerTime = wrGapBoundToRecordTime(
              distribution.wr_time,
              bin?.lower_bound,
            )
            const upperTime = wrGapBoundToRecordTime(
              distribution.wr_time,
              bin?.upper_bound,
            )
            const timeRangeLabel =
              lowerTime == null || upperTime == null
                ? null
                : `${formatWrGapAxisLabel(bin?.lower_bound ?? 0)} ~ ${formatWrGapAxisLabel(bin?.upper_bound ?? 0)} (${formatChartTimeSeconds(lowerTime)} to ${formatChartTimeSeconds(upperTime)})`
            const percentLabel = formatBucketPercent(
              value,
              distribution.plotted_pb_count ?? 0,
            )
            return `<div>
<div style="font-weight:600;">${escapeHtml(timeRangeLabel ?? `${formatWrGapAxisLabel(bin?.lower_bound ?? 0)} ~ ${formatWrGapAxisLabel(bin?.upper_bound ?? 0)}`)}</div>
<div style="margin-top:4px;">${escapeHtml(t("maps.stats.tooltipCountWithPercent", { count: value, percent: percentLabel }))}</div>
</div>`
          },
        },
        xAxis: {
          type: "value",
          inverse: true,
          min: xAxisMin,
          max: xAxisMax,
          interval: 0.5,
          axisLabel: {
            rotate: 0,
            fontSize: isNarrowViewport ? 10 : 11,
            color: axisColor,
            lineHeight: isNarrowViewport ? 16 : 18,
            rich: {
              gap: {
                fontSize: isNarrowViewport ? 10 : 11,
                fontWeight: 600,
                color: axisColor,
              },
              time: {
                fontSize: isNarrowViewport ? 9 : 10,
                color:
                  resolvedTheme === "dark"
                    ? "rgba(255, 255, 255, 0.56)"
                    : "rgba(15, 23, 42, 0.42)",
              },
            },
            formatter: (value) => {
              const numericValue = Number(value)
              const timeValue = wrGapBoundToRecordTime(
                distribution.wr_time,
                numericValue,
              )
              const timeLabel =
                timeValue == null
                  ? "--:--"
                  : formatChartTimeSeconds(timeValue)
              return `{gap|${formatWrGapAxisLabel(numericValue)}}\n{time|${timeLabel}}`
            },
          },
          axisLine: {
            onZero: false,
            lineStyle: {
              color: splitLineColor,
            },
          },
          splitLine: {
            show: false,
          },
        },
        yAxis: {
          type: "value",
          position: "left",
          min: 0,
          minInterval: 1,
          axisLine: {
            show: false,
            onZero: false,
            lineStyle: {
              color: splitLineColor,
            },
          },
          axisLabel: {
            color: axisColor,
          },
          axisTick: {
            show: false,
          },
          splitLine: {
            lineStyle: {
              color: splitLineColor,
            },
          },
        },
        series: [
          {
            type: "bar",
            data: barData,
            barWidth: "90%",
            itemStyle: barStyle,
            emphasis: {
              focus: "none",
              itemStyle: barHoverStyle,
            },
            blur: {
              itemStyle: barStyle,
            },
            select: {
              disabled: true,
              itemStyle: barStyle,
            },
            stateAnimation: {
              duration: 180,
              easing: "cubicOut",
            },
          },
        ],
        graphic: graphics.length > 0 ? graphics : undefined,
      }
    }

    const renderChart = () => {
      chart.setOption(buildOption())
    }

    renderChart()

    const resizeObserver = new ResizeObserver(() => {
      chart.resize()
      renderChart()
    })
    resizeObserver.observe(element)

    return () => {
      resizeObserver.disconnect()
      chart.dispose()
    }
  }, [barData, distribution.wr_time, isNarrowViewport, medianWrGap, playerWrGap, resolvedTheme, showPlayerMarker, t, visibleBins, xAxisMax, xAxisMin])

  const medianLabel = formatMedianWrGap(distribution.median_wr_gap)
  const medianTime = medianWrGapToRecordTime(
    distribution.wr_time,
    distribution.median_wr_gap,
  )
  const medianTimeLabel =
    medianTime == null
      ? t("common.notAvailable")
      : formatChartTimeSeconds(medianTime)

  return (
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            {title}
          </p>
          <div className="space-y-1 text-sm text-muted-foreground">
            <p>
              {t("maps.stats.medianLabel", {
                median: medianLabel ?? t("common.notAvailable"),
                time: medianTimeLabel,
              })}
            </p>
          </div>
        </div>
        {distribution.plotted_pb_count === 0 ? (
          <div className="flex h-72 items-center justify-center rounded-[18px] border border-dashed border-border/70 bg-muted/20 px-6 text-center text-sm text-muted-foreground">
            {t("maps.stats.empty")}
          </div>
        ) : (
          <div
            ref={chartRef}
            className="h-72 w-full"
            role="img"
            aria-label={title}
            data-testid={testId}
          />
        )}
      </CardContent>
    </Card>
  )
}

export function MapStatsSection({
  stats,
  nubPlayerRecordTime,
  proPlayerRecordTime,
  showPlayerMarker,
}: {
  stats: MapStatsPublic
  nubPlayerRecordTime: number | null
  proPlayerRecordTime: number | null
  showPlayerMarker: boolean
}) {
  const { t } = useTranslation()

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <WrGapDistributionChart
        distribution={stats.nub_wr_gap_distribution}
        title={t("maps.stats.nubTitle")}
        testId="map-stats-nub-wr-gap-chart"
        playerRecordTime={nubPlayerRecordTime}
        showPlayerMarker={showPlayerMarker}
      />
      <WrGapDistributionChart
        distribution={stats.pro_wr_gap_distribution}
        title={t("maps.stats.proTitle")}
        testId="map-stats-pro-wr-gap-chart"
        playerRecordTime={proPlayerRecordTime}
        showPlayerMarker={showPlayerMarker}
      />
    </div>
  )
}
