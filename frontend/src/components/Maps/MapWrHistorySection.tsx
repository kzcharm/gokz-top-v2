import { useQuery } from "@tanstack/react-query"
import type { EChartsOption, EChartsType } from "echarts"
import * as echarts from "echarts"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  MapsService,
  type MapWrHistoryEntryPublic,
  type RecordType,
} from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { getPlayerDisplayName } from "@/components/Common/PlayerDisplay"
import { formatRecordTime } from "@/components/Records/utils"
import type { AppScope } from "@/components/scope-provider"
import { useTheme } from "@/components/theme-provider"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

const HOLDER_COLORS = [
  "#4f46e5",
  "#0891b2",
  "#16a34a",
  "#ea580c",
  "#db2777",
  "#7c3aed",
  "#0f766e",
  "#b45309",
]

function getHolderName(row: MapWrHistoryEntryPublic) {
  return getPlayerDisplayName(row.player, row.player.steamid64)
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function getHolderColors(rows: MapWrHistoryEntryPublic[]) {
  const colors = new Map<string, string>()
  for (const row of rows) {
    if (!colors.has(row.player.steamid64)) {
      colors.set(
        row.player.steamid64,
        HOLDER_COLORS[colors.size % HOLDER_COLORS.length],
      )
    }
  }
  return colors
}

function buildSegments(rows: MapWrHistoryEntryPublic[]) {
  const segments: Array<{
    holderId: string
    rows: MapWrHistoryEntryPublic[]
  }> = []

  for (let index = 0; index + 1 < rows.length; index += 1) {
    const holderId = rows[index].player.steamid64
    const previousSegment = segments[segments.length - 1]
    if (previousSegment?.holderId === holderId) {
      previousSegment.rows.push(rows[index + 1])
    } else {
      segments.push({
        holderId,
        rows: [rows[index], rows[index + 1]],
      })
    }
  }

  return segments
}

function formatAxisDate(value: unknown) {
  const timestamp =
    typeof value === "number" ? value : Date.parse(String(value))
  if (!Number.isFinite(timestamp)) {
    return "-"
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(timestamp)
}

function WrHistoryChart({
  highlightedUuid,
  onHighlightedUuidChange,
  rows,
  xAxisMode,
}: {
  highlightedUuid: string | null
  onHighlightedUuidChange: (uuid: string | null) => void
  rows: MapWrHistoryEntryPublic[]
  xAxisMode: "time" | "record"
}) {
  const chartRef = useRef<HTMLDivElement | null>(null)
  const chartInstanceRef = useRef<EChartsType | null>(null)
  const { resolvedTheme } = useTheme()
  const [now, setNow] = useState(() => Date.now())
  const timeChartRows = useMemo(() => {
    const latestRow = rows[rows.length - 1]
    if (!latestRow || Date.parse(latestRow.created_on) >= now) {
      return rows
    }
    return [
      ...rows,
      {
        ...latestRow,
        created_on: new Date(now).toISOString(),
      },
    ]
  }, [now, rows])
  const chartRows = timeChartRows
  const holderColors = useMemo(() => getHolderColors(rows), [rows])
  const segments = useMemo(() => buildSegments(chartRows), [chartRows])

  useEffect(() => {
    const intervalId = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(intervalId)
  }, [])

  useEffect(() => {
    const element = chartRef.current
    if (!element || chartRows.length === 0 || chartInstanceRef.current) {
      return
    }

    const chart = echarts.init(element, undefined, { renderer: "svg" })
    chartInstanceRef.current = chart
    const resizeObserver = new ResizeObserver(() => chart.resize())
    resizeObserver.observe(element)

    const handlePointer = (params: unknown) => {
      const event = params as { data?: { rowIndex?: number } }
      const rowIndex = event.data?.rowIndex
      onHighlightedUuidChange(
        typeof rowIndex === "number"
          ? (chartRows[rowIndex]?.record_uuid ?? null)
          : null,
      )
    }
    const handleGlobalOut = () => onHighlightedUuidChange(null)
    chart.on("mouseover", handlePointer)
    chart.on("globalout", handleGlobalOut)

    return () => {
      chart.off("mouseover", handlePointer)
      chart.off("globalout", handleGlobalOut)
      resizeObserver.disconnect()
      chart.dispose()
      if (chartInstanceRef.current === chart) {
        chartInstanceRef.current = null
      }
    }
  }, [chartRows, onHighlightedUuidChange])

  useEffect(() => {
    const chart = chartInstanceRef.current
    if (!chart || chartRows.length === 0) {
      return
    }

    const axisColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.72)"
        : "rgba(15, 23, 42, 0.58)"
    const splitLineColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.1)"
        : "rgba(15, 23, 42, 0.1)"
    const currentWrTime = rows[rows.length - 1]?.time ?? 0
    const slowestWrTime = rows.reduce(
      (slowest, row) => Math.max(slowest, row.time),
      currentWrTime,
    )
    const axisMax =
      slowestWrTime > currentWrTime
        ? slowestWrTime
        : currentWrTime + Math.max(currentWrTime * 0.1, 1)
    const getChartXValue = (rowIndex: number) =>
      xAxisMode === "time"
        ? Date.parse(chartRows[rowIndex]?.created_on ?? "")
        : rowIndex
    const xRange = Math.abs(
      getChartXValue(chartRows.length - 1) - getChartXValue(0),
    )
    const nearbyXDistance = xRange > 0 ? xRange * 0.06 : 1
    const verticalXDistance = xRange > 0 ? xRange * 0.01 : 1

    const option: EChartsOption = {
      animationDuration: 280,
      grid: { top: 56, right: 24, bottom: 54, left: 74 },
      tooltip: {
        trigger: "item",
        formatter: (params) => {
          const data = (params as { data?: { rowIndex?: number } }).data
          const row =
            typeof data?.rowIndex === "number" ? chartRows[data.rowIndex] : null
          if (!row) return ""
          return `<div><div style="font-weight:600;">${escapeHtml(getHolderName(row))} · ${formatRecordTime(row.time)}</div><div style="margin-top:4px;">${formatAxisDate(Date.parse(row.created_on))} · ${escapeHtml(row.mode)} · ${escapeHtml(row.server_name)}</div></div>`
        },
      },
      legend: { show: false },
      xAxis: {
        type: xAxisMode === "time" ? "time" : "category",
        ...(xAxisMode === "record"
          ? { data: chartRows.map((row) => row.created_on) }
          : {}),
        axisLabel: {
          color: axisColor,
          hideOverlap: true,
          formatter: (value: string | number) => formatAxisDate(value),
        },
        axisLine: { lineStyle: { color: splitLineColor } },
      },
      yAxis: {
        type: "value",
        inverse: true,
        min: currentWrTime,
        max: axisMax,
        name: "Run Time",
        nameLocation: "middle",
        nameGap: 52,
        axisLabel: {
          color: axisColor,
          formatter: (value: number) => formatRecordTime(value),
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: splitLineColor } },
      },
      series: segments.map((segment) => ({
        type: "line",
        name: segment.holderId,
        smooth: true,
        showSymbol: true,
        symbol: "circle",
        symbolSize: 8,
        label: {
          position: "top",
          color: holderColors.get(segment.holderId),
          fontSize: 11,
          lineHeight: 14,
          formatter: (params) => {
            const data = (params as { data?: { rowIndex?: number } }).data
            const rowIndex = data?.rowIndex
            if (typeof rowIndex !== "number" || rowIndex >= rows.length) {
              return ""
            }
            const row = chartRows[rowIndex]
            return row
              ? `${getHolderName(row)}\n${formatRecordTime(row.time)}`
              : ""
          },
        },
        labelLayout: { hideOverlap: true },
        lineStyle: { color: holderColors.get(segment.holderId), width: 3 },
        itemStyle: { color: holderColors.get(segment.holderId) },
        data: segment.rows.map((row) => {
          const rowIndex = chartRows.indexOf(row)
          const nextRow = chartRows[rowIndex + 1]
          const previousRow = chartRows[rowIndex - 1]
          const currentX = getChartXValue(rowIndex)
          const nextX = getChartXValue(rowIndex + 1)
          const previousX = getChartXValue(rowIndex - 1)
          const outgoingLineCrossesLabel =
            nextRow &&
            nextRow.time < row.time &&
            Math.abs(nextX - currentX) <= nearbyXDistance
          const incomingLineCrossesLabel =
            previousRow &&
            row.time < previousRow.time &&
            Math.abs(currentX - previousX) <= nearbyXDistance
          const outgoingXDelta = nextX - currentX
          const outgoingIsVertical =
            Math.abs(outgoingXDelta) <= verticalXDistance
          const labelPlacement = outgoingLineCrossesLabel
            ? outgoingIsVertical
              ? ({
                  position: "right",
                  align: "left",
                  verticalAlign: "top",
                } as const)
              : outgoingXDelta > 0
                ? ({
                    position: "top",
                    align: "right",
                    verticalAlign: "bottom",
                  } as const)
                : ({
                    position: "top",
                    align: "left",
                    verticalAlign: "bottom",
                  } as const)
            : incomingLineCrossesLabel
              ? ({
                  position: "top",
                  align: "right",
                  verticalAlign: "bottom",
                } as const)
              : ({ position: "top", verticalAlign: "bottom" } as const)
          return {
            value: [
              xAxisMode === "time" ? Date.parse(row.created_on) : rowIndex,
              row.time,
            ],
            rowIndex,
            label: {
              show:
                rowIndex < rows.length &&
                segment.holderId === row.player.steamid64,
              ...labelPlacement,
            },
          }
        }),
      })),
    }

    chart.setOption(option, { notMerge: true })
  }, [chartRows, holderColors, resolvedTheme, rows, segments, xAxisMode])

  useEffect(() => {
    const chart = chartInstanceRef.current
    if (!chart) return
    chart.dispatchAction({ type: "downplay", seriesIndex: "all" })
    const seriesIndex = segments.findIndex((segment) =>
      segment.rows.some((row) => row.record_uuid === highlightedUuid),
    )
    if (seriesIndex < 0) {
      chart.dispatchAction({ type: "hideTip" })
      return
    }
    const dataIndex = segments[seriesIndex].rows.findIndex(
      (row) => row.record_uuid === highlightedUuid,
    )
    chart.dispatchAction({ type: "showTip", seriesIndex, dataIndex })
  }, [highlightedUuid, segments])

  if (rows.length === 0) {
    return null
  }

  return (
    <div
      ref={chartRef}
      className="h-80 w-full"
      data-testid="map-wr-history-chart"
      role="img"
      aria-label="World record history line chart"
    />
  )
}

export function MapWrHistorySection({
  mapId,
  scope,
  type,
}: {
  mapId: number
  scope: AppScope
  type: RecordType
}) {
  const { t } = useTranslation()
  const [highlightedUuid, setHighlightedUuid] = useState<string | null>(null)
  const [xAxisMode, setXAxisMode] = useState<"time" | "record">("time")
  const historyQuery = useQuery({
    queryKey: ["map", "wr-history", mapId, scope, type],
    queryFn: () => MapsService.readMapWrHistory({ mapId, scope, type }),
    staleTime: 30_000,
    retry: false,
  })
  const rows = historyQuery.data?.data ?? []
  const eventRows = useMemo(() => [...rows].reverse(), [rows])
  const holderColors = useMemo(() => getHolderColors(rows), [rows])
  const holders = useMemo(() => {
    const seen = new Set<string>()
    return rows.filter((row) => {
      if (seen.has(row.player.steamid64)) return false
      seen.add(row.player.steamid64)
      return true
    })
  }, [rows])

  if (historyQuery.isLoading) {
    return (
      <Card className="rounded-[26px] border-border/70 bg-card/95 py-0">
        <CardContent className="space-y-5 p-6">
          <Skeleton className="h-6 w-56" />
          <Skeleton className="h-80 w-full rounded-[18px]" />
          <Skeleton className="h-12 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (historyQuery.isError) {
    return (
      <Card className="rounded-[26px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 text-sm text-destructive">
          {t("maps.wrHistory.loadFailedBody")}
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-6 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">
              {t("maps.wrHistory.title")}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("maps.wrHistory.description")}
            </p>
          </div>
          <Tabs
            value={xAxisMode}
            onValueChange={(value) => {
              if (value === "time" || value === "record") {
                setXAxisMode(value)
              }
            }}
          >
            <TabsList className="w-fit">
              <TabsTrigger value="time">
                {t("maps.wrHistory.xAxis.time")}
              </TabsTrigger>
              <TabsTrigger value="record">
                {t("maps.wrHistory.xAxis.record")}
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {rows.length === 0 ? (
          <div className="flex h-48 items-center justify-center rounded-[18px] border border-dashed border-border/70 bg-muted/20 px-6 text-center text-sm text-muted-foreground">
            {t("maps.wrHistory.empty")}
          </div>
        ) : (
          <>
            <WrHistoryChart
              highlightedUuid={highlightedUuid}
              onHighlightedUuidChange={setHighlightedUuid}
              rows={rows}
              xAxisMode={xAxisMode}
            />
            <div
              className="flex flex-wrap gap-x-5 gap-y-2 border-t border-border/60 pt-4"
              data-testid="map-wr-history-legend"
            >
              {holders.map((row) => (
                <div
                  key={row.player.steamid64}
                  className="flex items-center gap-2 text-sm"
                >
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{
                      backgroundColor: holderColors.get(row.player.steamid64),
                    }}
                    aria-hidden="true"
                  />
                  <span>{getHolderName(row)}</span>
                </div>
              ))}
            </div>
            <div
              className="max-h-72 overflow-y-auto rounded-lg border border-border/70"
              data-testid="map-wr-history-events"
            >
              {eventRows.map((row) => (
                <button
                  type="button"
                  key={row.record_uuid}
                  className={cn(
                    "flex w-full flex-wrap items-center gap-x-4 gap-y-1 border-b border-border/60 px-3 py-3 text-left text-sm last:border-b-0",
                    highlightedUuid === row.record_uuid && "bg-primary/8",
                  )}
                  onMouseEnter={() => setHighlightedUuid(row.record_uuid)}
                  onMouseLeave={() => setHighlightedUuid(null)}
                >
                  <span className="font-mono text-base font-semibold">
                    {formatRecordTime(row.time)}
                  </span>
                  <span
                    className="font-medium"
                    style={{ color: holderColors.get(row.player.steamid64) }}
                  >
                    {getHolderName(row)}
                  </span>
                  <span className="text-muted-foreground">
                    {row.mode} · {row.server_name}
                  </span>
                  <FormattedDateTime
                    value={row.created_on}
                    className="ml-auto text-xs text-muted-foreground"
                  />
                </button>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
