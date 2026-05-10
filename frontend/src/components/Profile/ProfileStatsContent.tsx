import type { EChartsOption, EChartsType } from "echarts"
import * as echarts from "echarts"
import { Pause, Play } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import type {
  PlayerMostPlayedServerPeriodPublic,
  PlayerMostPlayedServerPublic,
} from "@/client"
import { formatSecondsAsHours } from "@/components/Profile/profile-utils"
import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useMediaQuery } from "@/hooks/useMobile"
import { cn } from "@/lib/utils"

const ALL_TIME_VIEW_ID = "all-time"
const LAST_365_DAYS_VIEW_ID = "last-365-days"
const AUTOPLAY_INTERVAL_MS = 2000
const PIE_LABEL_PERCENT_THRESHOLD = 8

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function buildChartColorPalette(): string[] {
  return [
    "#4299E1",
    "#48BB78",
    "#ED8936",
    "#9F7AEA",
    "#F56565",
    "#38B2AC",
    "#ECC94B",
    "#F6AD55",
    "#4FD1C7",
    "#A78BFA",
    "#FC8181",
    "#63B3ED",
    "#68D391",
    "#FBB6CE",
    "#90CDF4",
    "#C6F6D5",
  ]
}

function getViewEntry(
  stat: PlayerMostPlayedServerPublic,
  viewId: string,
): PlayerMostPlayedServerPeriodPublic {
  const fallback: PlayerMostPlayedServerPeriodPublic = {
    total_seconds: 0,
    entries: [],
  }

  if (viewId === ALL_TIME_VIEW_ID) {
    return stat.all_time ?? fallback
  }

  if (viewId === LAST_365_DAYS_VIEW_ID) {
    return stat.last_365_days ?? fallback
  }

  return stat.yearly?.[viewId] ?? fallback
}

function ProfileStatsPieCard({ stat }: { stat: PlayerMostPlayedServerPublic }) {
  const { t } = useTranslation()
  const chartRef = useRef<HTMLDivElement | null>(null)
  const chartInstanceRef = useRef<EChartsType | null>(null)
  const { resolvedTheme } = useTheme()
  const isNarrowViewport = useMediaQuery("(max-width: 1023px)")

  const yearViewIds = useMemo(
    () =>
      (stat.years ?? [])
        .map((year) => String(year))
        .sort((left, right) => Number(left) - Number(right)),
    [stat.years],
  )
  const orderedViewIds = useMemo(
    () => [...yearViewIds, LAST_365_DAYS_VIEW_ID, ALL_TIME_VIEW_ID],
    [yearViewIds],
  )
  const defaultViewId = orderedViewIds[0] ?? ALL_TIME_VIEW_ID
  const [activeViewId, setActiveViewId] = useState<string>(defaultViewId)
  const [isPlaying, setIsPlaying] = useState(false)

  useEffect(() => {
    const allowedViews = new Set(orderedViewIds)
    setActiveViewId((currentViewId) =>
      allowedViews.has(currentViewId) ? currentViewId : defaultViewId,
    )
    if (yearViewIds.length === 0) {
      setIsPlaying(false)
    }
  }, [defaultViewId, orderedViewIds, yearViewIds.length])

  useEffect(() => {
    if (!isPlaying || orderedViewIds.length === 0) {
      return
    }

    const intervalId = window.setInterval(() => {
      setActiveViewId((currentViewId) => {
        const currentIndex = orderedViewIds.indexOf(currentViewId)
        if (currentIndex < 0) {
          return orderedViewIds[0]
        }

        return orderedViewIds[(currentIndex + 1) % orderedViewIds.length]
      })
    }, AUTOPLAY_INTERVAL_MS)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [isPlaying, orderedViewIds])

  const activePeriod = useMemo(
    () => getViewEntry(stat, activeViewId),
    [activeViewId, stat],
  )
  const activePeriodEntries = activePeriod.entries ?? []
  const totalSeconds = activePeriod.total_seconds ?? 0
  const chartData = useMemo(
    () =>
      activePeriodEntries.map((entry) => ({
        id: entry.key,
        name: entry.label,
        value: entry.total_seconds ?? 0,
        key: entry.key,
        serverCount: entry.server_count,
        percentage:
          totalSeconds > 0
            ? ((entry.total_seconds ?? 0) / totalSeconds) * 100
            : 0,
      })),
    [activePeriodEntries, totalSeconds],
  )
  const colorByKey = useMemo(() => {
    const palette = buildChartColorPalette()
    const byKey = new Map<string, string>()

    for (const [index, entry] of (stat.all_time?.entries ?? []).entries()) {
      byKey.set(entry.key, palette[index % palette.length])
    }

    return byKey
  }, [stat.all_time?.entries])
  const hasChartData = chartData.length > 0 && totalSeconds > 0
  const totalLabel = formatSecondsAsHours(totalSeconds)
  const activeLabel =
    activeViewId === ALL_TIME_VIEW_ID
      ? t("profile.stats.allTime")
      : activeViewId === LAST_365_DAYS_VIEW_ID
        ? t("profile.stats.last365Days")
        : activeViewId

  useEffect(() => {
    const element = chartRef.current
    if (!element || !hasChartData || chartInstanceRef.current) {
      return
    }

    const chart = echarts.init(element, undefined, {
      renderer: "svg",
    })
    chartInstanceRef.current = chart

    const resizeObserver = new ResizeObserver(() => {
      chart.resize()
    })
    resizeObserver.observe(element)

    return () => {
      resizeObserver.disconnect()
      chart.dispose()
      if (chartInstanceRef.current === chart) {
        chartInstanceRef.current = null
      }
    }
  }, [hasChartData])

  useEffect(() => {
    const chart = chartInstanceRef.current
    if (!chart) {
      return
    }

    const palette = buildChartColorPalette()
    const textColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.84)"
        : "rgba(15, 23, 42, 0.88)"
    const mutedTextColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.62)"
        : "rgba(15, 23, 42, 0.64)"
    const gridColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.12)"
        : "rgba(15, 23, 42, 0.1)"
    const shadowColor = "rgba(0, 0, 0, 0.18)"
    const activeTotalSeconds = totalSeconds
    const showSliceLabels = !isNarrowViewport

    const option: EChartsOption = {
      backgroundColor: "transparent",
      color: palette,
      animationDuration: 650,
      animationDurationUpdate: 1100,
      animationEasing: "cubicOut",
      animationEasingUpdate: "cubicOut",
      tooltip: {
        trigger: "item",
        backgroundColor:
          resolvedTheme === "dark"
            ? "rgba(15, 23, 42, 0.95)"
            : "rgba(255, 255, 255, 0.96)",
        borderColor: gridColor,
        textStyle: {
          color: textColor,
        },
        formatter: (params) => {
          const entry = params as {
            name?: string
            value?: number | string
            data?: { serverCount?: number }
            percent?: number
          }
          const label = String(entry.name ?? "")
          const value = Number(entry.value ?? 0)
          const percentage = Number(entry.percent ?? 0).toFixed(1)
          const serverCount = entry.data?.serverCount ?? 0
          const serverCountLabel =
            serverCount > 1
              ? `<div style="margin-top:4px;">${escapeHtml(
                  t("profile.stats.tooltipServers", {
                    count: serverCount,
                  }),
                )}</div>`
              : ""

          return `<div>
<div style="font-weight:600;">${escapeHtml(label)}</div>
<div style="margin-top:4px;">${escapeHtml(
            t("profile.stats.tooltipHours", {
              hours: formatSecondsAsHours(value),
              percent: percentage,
            }),
          )}</div>
${serverCountLabel}
</div>`
        },
      },
      legend: {
        type: "scroll",
        orient: isNarrowViewport ? "horizontal" : "vertical",
        top: isNarrowViewport ? undefined : "middle",
        bottom: isNarrowViewport ? 0 : undefined,
        left: isNarrowViewport ? 0 : 0,
        right: isNarrowViewport ? 0 : undefined,
        textStyle: {
          color: mutedTextColor,
        },
      },
      series: [
        {
          name: activeLabel,
          type: "pie",
          radius: isNarrowViewport ? ["38%", "60%"] : ["42%", "68%"],
          center: isNarrowViewport ? ["50%", "42%"] : ["56%", "52%"],
          avoidLabelOverlap: true,
          minAngle: 3,
          universalTransition: true,
          itemStyle: {
            borderColor: isNarrowViewport
              ? gridColor
              : resolvedTheme === "dark"
                ? "#1A202C"
                : "#FFFFFF",
            borderWidth: 2,
            borderRadius: 8,
          },
          emphasis: {
            scale: false,
            focus: "none",
            label: {
              show: true,
              color: textColor,
              fontWeight: 600,
              formatter: (params: { name?: string; value?: unknown }) => {
                const value = Number(params.value ?? 0)
                const percentage =
                  activeTotalSeconds > 0
                    ? ((value / activeTotalSeconds) * 100).toFixed(1)
                    : "0.0"
                return `${String(params.name ?? "")}\n${percentage}%`
              },
            },
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor,
            },
            labelLine: {
              show: true,
              lineStyle: {
                color: mutedTextColor,
              },
            },
          },
          data: chartData.map((entry, index) => {
            const shouldShowLabel =
              showSliceLabels &&
              (entry.percentage ?? 0) >= PIE_LABEL_PERCENT_THRESHOLD
            return {
              id: entry.id,
              name: entry.name,
              value: entry.value,
              itemStyle: {
                color:
                  colorByKey.get(entry.key) ?? palette[index % palette.length],
              },
              label: {
                show: shouldShowLabel,
                color: textColor,
                fontWeight: 600,
                formatter: (params: { name?: string; value?: unknown }) => {
                  const value = Number(params.value ?? 0)
                  const percentage =
                    activeTotalSeconds > 0
                      ? ((value / activeTotalSeconds) * 100).toFixed(1)
                      : "0.0"
                  return `${String(params.name ?? "")}\n${percentage}%`
                },
              },
              labelLine: {
                show: shouldShowLabel,
                lineStyle: {
                  color: mutedTextColor,
                },
              },
            }
          }),
        },
      ],
    }

    chart.setOption(option, {
      lazyUpdate: true,
      notMerge: false,
    })
  }, [
    activeLabel,
    chartData,
    colorByKey,
    isNarrowViewport,
    resolvedTheme,
    t,
    totalSeconds,
  ])

  return (
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              {t("profile.stats.title")}
            </p>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => {
                if (yearViewIds.length === 0) {
                  return
                }

                setActiveViewId((currentViewId) =>
                  orderedViewIds.includes(currentViewId)
                    ? currentViewId
                    : orderedViewIds[0],
                )
                setIsPlaying((current) => !current)
              }}
              disabled={orderedViewIds.length === 0}
              aria-label={
                isPlaying ? t("profile.stats.pause") : t("profile.stats.play")
              }
              title={
                isPlaying ? t("profile.stats.pause") : t("profile.stats.play")
              }
              data-testid="profile-stats-playback-button"
              className="shrink-0"
            >
              {isPlaying ? <Pause /> : <Play />}
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex min-w-0 gap-2 overflow-x-auto">
              {orderedViewIds.map((viewId) => {
                const label =
                  viewId === ALL_TIME_VIEW_ID
                    ? t("profile.stats.allTime")
                    : viewId === LAST_365_DAYS_VIEW_ID
                      ? t("profile.stats.last365Days")
                      : viewId

                return (
                  <Button
                    key={viewId}
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setActiveViewId(viewId)
                      setIsPlaying(false)
                    }}
                    className={cn(
                      "shrink-0",
                      activeViewId === viewId && "bg-card text-foreground",
                    )}
                    data-testid={`profile-stats-view-${viewId}`}
                  >
                    {label}
                  </Button>
                )
              })}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
          <span>{activeLabel}</span>
          <span>{t("profile.stats.totalPlaytime", { total: totalLabel })}</span>
        </div>

        {!hasChartData ? (
          <div className="flex h-[22rem] items-center justify-center rounded-[18px] border border-dashed border-border/70 bg-background/50 text-sm text-muted-foreground">
            {t("profile.stats.empty")}
          </div>
        ) : (
          <div
            ref={chartRef}
            className="h-[22rem] w-full"
            role="img"
            aria-label={t("profile.stats.ariaLabel", { view: activeLabel })}
            data-testid="profile-stats-most-played-server-chart"
          />
        )}
      </CardContent>
    </Card>
  )
}

function ProfileStatsSkeleton() {
  return (
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="space-y-2">
          <Skeleton className="h-4 w-44" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-10 w-full rounded-full" />
        <Skeleton className="h-[22rem] w-full rounded-[18px]" />
      </CardContent>
    </Card>
  )
}

export function ProfileStatsContent({
  error,
  loading,
  mostPlayedServer,
}: {
  error: boolean
  loading: boolean
  mostPlayedServer: PlayerMostPlayedServerPublic | null
}) {
  const { t } = useTranslation()

  if (loading) {
    return <ProfileStatsSkeleton />
  }

  if (error) {
    return (
      <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 text-sm text-destructive">
          {t("profile.stats.loadFailed")}
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      {mostPlayedServer ? (
        <ProfileStatsPieCard stat={mostPlayedServer} />
      ) : (
        <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0 xl:col-span-2">
          <CardContent className="p-6 text-sm text-muted-foreground">
            {t("profile.stats.empty")}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
