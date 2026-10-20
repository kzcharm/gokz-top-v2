import type { EChartsOption } from "echarts"
import * as echarts from "echarts"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useTheme } from "@/components/theme-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useMediaQuery } from "@/hooks/useMobile"
import { cn } from "@/lib/utils"
import type { ProfileRecordDistributionBin } from "./profile-record-distribution"

const PROFILE_DISTRIBUTION_TWO_COLUMN_MIN_WIDTH = 1080
function DistributionCardsSkeleton({ twoColumns }: { twoColumns: boolean }) {
  return (
    <div className={cn("grid gap-6", twoColumns && "xl:grid-cols-2")}>
      {Array.from({ length: 2 }, (_, index) => (
        <Card
          key={index}
          className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0"
        >
          <CardContent className="space-y-5 p-6">
            <div className="space-y-2">
              <Skeleton className="h-4 w-44" />
              <Skeleton className="h-4 w-28" />
            </div>
            <Skeleton className="h-72 w-full rounded-[18px]" />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function ProfileDistributionChart({
  bins,
  title,
  color,
}: {
  bins: ProfileRecordDistributionBin[]
  title: string
  color: string
}) {
  const { t } = useTranslation()
  const chartRef = useRef<HTMLDivElement | null>(null)
  const { resolvedTheme } = useTheme()
  const isNarrowViewport = useMediaQuery("(max-width: 1439px)")

  useEffect(() => {
    const element = chartRef.current
    if (!element) {
      return
    }

    const chart = echarts.init(element)
    const labels = bins.map((bin) => bin.label)
    const counts = bins.map((bin) => bin.count)
    const axisColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.52)"
        : "rgba(15, 23, 42, 0.58)"
    const splitLineColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.08)"
        : "rgba(15, 23, 42, 0.08)"

    const option: EChartsOption = {
      animationDuration: 250,
      animationDurationUpdate: 180,
      grid: {
        top: 24,
        right: 16,
        bottom: 76,
        left: 44,
      },
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "shadow",
        },
        formatter: (params) => {
          const [entry] = Array.isArray(params) ? params : [params]
          if (!entry) {
            return ""
          }
          const value =
            typeof entry.value === "number" ? entry.value : Number(entry.value)
          const hoveredBin = bins.find(
            (bin) => bin.label === String(entry.name ?? ""),
          )
          const mapNamesMarkup =
            hoveredBin && hoveredBin.topMapNames.length > 0
              ? `<div style="margin-top:8px;font-size:12px;line-height:1.5;">
${hoveredBin.topMapNames
  .map((mapName) => `<div>${escapeHtml(mapName)}</div>`)
  .join("")}
${hoveredBin.hasMoreMapNames ? "<div>...</div>" : ""}
</div>`
              : ""

          return `<div>
<div style="font-weight:600;">${escapeHtml(String(entry.name ?? ""))}</div>
<div style="margin-top:4px;">${escapeHtml(t("profile.distribution.tooltipCount", { count: value }))}</div>
${mapNamesMarkup}
</div>`
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisTick: {
          alignWithLabel: true,
        },
        axisLabel: {
          interval: 0,
          rotate: isNarrowViewport ? 55 : 40,
          fontSize: isNarrowViewport ? 10 : 11,
          color: axisColor,
        },
        axisLine: {
          lineStyle: {
            color: splitLineColor,
          },
        },
      },
      yAxis: {
        type: "value",
        min: 0,
        minInterval: 1,
        axisLabel: {
          color: axisColor,
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
          data: counts,
          barMaxWidth: 22,
          itemStyle: {
            color,
            borderRadius: [6, 6, 0, 0],
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 14,
              shadowColor:
                resolvedTheme === "dark"
                  ? "rgba(255, 255, 255, 0.12)"
                  : "rgba(15, 23, 42, 0.16)",
            },
          },
        },
      ],
    }

    chart.setOption(option)

    const resizeObserver = new ResizeObserver(() => {
      chart.resize()
    })
    resizeObserver.observe(element)

    return () => {
      resizeObserver.disconnect()
      chart.dispose()
    }
  }, [bins, color, isNarrowViewport, resolvedTheme, t])

  return (
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            {title}
          </p>
        </div>
        <div
          ref={chartRef}
          className="h-72 w-full"
          role="img"
          aria-label={title}
        />
      </CardContent>
    </Card>
  )
}

export function ProfileRecordDistributionSection({
  nubRecordDistribution,
  proRecordDistribution,
  recordDistributionError,
  recordDistributionLoading,
}: {
  nubRecordDistribution: ProfileRecordDistributionBin[]
  proRecordDistribution: ProfileRecordDistributionBin[]
  recordDistributionError: boolean
  recordDistributionLoading: boolean
}) {
  const { t } = useTranslation()
  const contentRef = useRef<HTMLDivElement | null>(null)
  const [contentWidth, setContentWidth] = useState(0)

  useEffect(() => {
    const element = contentRef.current
    if (!element) {
      return
    }

    const updateWidth = () => {
      setContentWidth(element.getBoundingClientRect().width)
    }

    updateWidth()

    const observer = new ResizeObserver(() => {
      updateWidth()
    })
    observer.observe(element)

    return () => {
      observer.disconnect()
    }
  }, [])

  const showTwoColumns =
    contentWidth >= PROFILE_DISTRIBUTION_TWO_COLUMN_MIN_WIDTH

  return (
    <div ref={contentRef} className="min-w-0">
      {recordDistributionError ? (
        <Alert variant="destructive">
          <AlertTitle>{t("profile.distribution.loadFailedTitle")}</AlertTitle>
          <AlertDescription>
            {t("profile.distribution.loadFailedBody")}
          </AlertDescription>
        </Alert>
      ) : recordDistributionLoading ? (
        <DistributionCardsSkeleton twoColumns={showTwoColumns} />
      ) : (
        <div className={cn("grid gap-6", showTwoColumns && "xl:grid-cols-2")}>
          <ProfileDistributionChart
            bins={nubRecordDistribution}
            title={t("profile.distribution.nubTitle")}
            color="#f3c40f"
          />
          <ProfileDistributionChart
            bins={proRecordDistribution}
            title={t("profile.distribution.proTitle")}
            color="#3598db"
          />
        </div>
      )}
    </div>
  )
}
