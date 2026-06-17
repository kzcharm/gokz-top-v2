import { useQuery } from "@tanstack/react-query"
import type { EChartsOption, EChartsType } from "echarts"
import * as echarts from "echarts"
import { LineChart } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import type { RecordPublic, RecordRunHistoryEntryPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import type { AppScope } from "@/components/scope-provider"
import { useTheme } from "@/components/theme-provider"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

import { getRecordRunHistoryQueryOptions } from "./pb-records-utils"
import { formatRecordTime } from "./utils"

type RunHistoryRecordType = "NUB" | "PRO"

function getRunDayKey(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function collapseRunsToBestPerDay(rows: RecordRunHistoryEntryPublic[]) {
  const bestByDay = new Map<string, RecordRunHistoryEntryPublic>()

  for (const row of rows) {
    const dayKey = getRunDayKey(row.created_on)
    const existingRow = bestByDay.get(dayKey)
    if (!existingRow || row.time < existingRow.time) {
      bestByDay.set(dayKey, row)
    }
  }

  return rows.filter(
    (row) => bestByDay.get(getRunDayKey(row.created_on)) === row,
  )
}

function getChronologicalRows(rows: RecordRunHistoryEntryPublic[]) {
  return [...rows].sort((left, right) => {
    const dateComparison =
      Date.parse(left.created_on) - Date.parse(right.created_on)
    if (dateComparison !== 0) {
      return dateComparison
    }
    return left.time - right.time
  })
}

function getPreviousPbDeltaByUuid(rows: RecordRunHistoryEntryPublic[]) {
  const deltaByUuid = new Map<string, number>()
  let lastPbTime: number | null = null

  for (const row of getChronologicalRows(rows)) {
    if (lastPbTime != null) {
      deltaByUuid.set(row.uuid, row.time - lastPbTime)
    }

    if (row.is_pb) {
      lastPbTime = row.time
    }
  }

  return deltaByUuid
}

function getCurrentPbRun(rows: RecordRunHistoryEntryPublic[]) {
  const pbRows = getChronologicalRows(rows).filter((row) => row.is_pb)
  return pbRows[pbRows.length - 1] ?? null
}

function getRunTimeDeltaLabel(delta: number) {
  const sign = delta < 0 ? "-" : "+"
  return `${sign}${formatRecordTime(Math.abs(delta))}`
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function wrGapToRecordTime(
  wrTime: number | null | undefined,
  wrGap: number | null | undefined,
) {
  if (
    wrTime == null ||
    !Number.isFinite(wrTime) ||
    wrTime <= 0 ||
    wrGap == null ||
    !Number.isFinite(wrGap)
  ) {
    return null
  }

  return wrTime * (1 + 2 ** wrGap)
}

function getAxisPointerDataIndex(
  value: string | number | undefined,
  rows: RecordRunHistoryEntryPublic[],
) {
  if (value == null) {
    return -1
  }

  if (typeof value === "number" && Number.isInteger(value)) {
    return value >= 0 && value < rows.length ? value : -1
  }

  return rows.findIndex((row) => row.created_on === String(value))
}

function RunHistoryChart({
  currentPbUuid,
  deltaByUuid,
  highlightedUuid,
  onHighlightedUuidChange,
  rows,
  wrTime,
}: {
  currentPbUuid: string | null
  deltaByUuid: Map<string, number>
  highlightedUuid: string | null
  onHighlightedUuidChange: (uuid: string | null) => void
  rows: RecordRunHistoryEntryPublic[]
  wrTime: number | null | undefined
}) {
  const chartRef = useRef<HTMLDivElement | null>(null)
  const chartInstanceRef = useRef<EChartsType | null>(null)
  const { resolvedTheme } = useTheme()
  const { formatDateTime } = useDateTimeFormat()
  const chartRows = useMemo(
    () =>
      rows.filter((row) => row.wr_gap != null && Number.isFinite(row.wr_gap)),
    [rows],
  )
  const hasChartData = chartRows.length > 0

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

    const axisColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.72)"
        : "rgba(15, 23, 42, 0.58)"
    const splitLineColor =
      resolvedTheme === "dark"
        ? "rgba(255, 255, 255, 0.08)"
        : "rgba(15, 23, 42, 0.08)"
    const lineColor =
      resolvedTheme === "dark"
        ? "oklch(0.6801 0.1583 276.9349)"
        : "oklch(0.5106 0.2301 276.9656)"

    const option: EChartsOption = {
      animationDuration: 280,
      animationDurationUpdate: 180,
      grid: {
        top: 28,
        right: 24,
        bottom: 44,
        left: 72,
      },
      tooltip: {
        trigger: "axis",
        triggerOn: "mousemove|click",
        axisPointer: {
          type: "line",
          snap: true,
          lineStyle: {
            color: lineColor,
            opacity: 0.28,
            width: 1,
          },
        },
        formatter: (params) => {
          const entry = Array.isArray(params) ? params[0] : params
          const dataIndex =
            entry && typeof entry.dataIndex === "number" ? entry.dataIndex : -1
          const row = dataIndex >= 0 ? chartRows[dataIndex] : undefined
          if (!row) {
            return ""
          }

          const delta = deltaByUuid.get(row.uuid)
          const deltaLabel = delta == null ? null : getRunTimeDeltaLabel(delta)
          const deltaColor =
            delta == null
              ? null
              : delta < 0
                ? "oklch(0.627 0.194 149.214)"
                : "oklch(0.577 0.245 27.325)"
          const pbLabel =
            row.uuid === currentPbUuid
              ? "Current PB"
              : row.is_pb
                ? "PB run"
                : "Run"
          return `<div>
<div style="font-weight:600;">${escapeHtml(pbLabel)} · ${escapeHtml(formatRecordTime(row.time))}</div>
${deltaLabel ? `<div style="margin-top:4px;color:${deltaColor};font-weight:600;">${escapeHtml(deltaLabel)} vs last PB</div>` : ""}
<div style="margin-top:4px;">${escapeHtml(row.server_name)} · ${escapeHtml(formatDateTime(row.created_on, { display: "absolute", fallback: "-" }))}</div>
<div style="margin-top:4px;">${escapeHtml(row.mode)} · ${row.teleports} TP</div>
</div>`
        },
      },
      xAxis: {
        type: "category",
        data: chartRows.map((row) => row.created_on),
        name: "Date",
        nameLocation: "middle",
        nameGap: 30,
        axisLabel: {
          color: axisColor,
          hideOverlap: true,
          formatter: (value) =>
            formatDateTime(String(value), {
              dateOnly: true,
              display: "absolute",
              fallback: "-",
            }),
        },
        axisLine: {
          lineStyle: {
            color: splitLineColor,
          },
        },
        splitLine: {
          show: false,
        },
        axisPointer: {
          snap: true,
        },
      },
      yAxis: {
        type: "value",
        inverse: true,
        name: "Run Time",
        nameGap: 46,
        nameLocation: "middle",
        axisLabel: {
          color: axisColor,
          formatter: (value) => {
            const recordTime = wrGapToRecordTime(wrTime, Number(value))
            return recordTime == null ? "-" : formatRecordTime(recordTime)
          },
        },
        axisLine: {
          show: false,
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
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 7,
          lineStyle: {
            color: lineColor,
            width: 3,
          },
          itemStyle: {
            color: lineColor,
          },
          emphasis: {
            scale: 1.8,
            focus: "none",
            lineStyle: {
              color: lineColor,
              width: 3,
            },
            itemStyle: {
              color: lineColor,
              borderColor:
                resolvedTheme === "dark"
                  ? "rgba(255, 255, 255, 0.9)"
                  : "rgba(255, 255, 255, 0.96)",
              borderWidth: 3,
              shadowBlur: 10,
              shadowColor:
                resolvedTheme === "dark"
                  ? "rgba(129, 140, 248, 0.55)"
                  : "rgba(79, 70, 229, 0.3)",
            },
          },
          data: chartRows.map((row) =>
            row.uuid === currentPbUuid
              ? {
                  value: row.wr_gap,
                  symbolSize: 11,
                  itemStyle: {
                    color: "oklch(0.7686 0.1647 70.0804)",
                    borderColor:
                      resolvedTheme === "dark"
                        ? "rgba(255, 255, 255, 0.92)"
                        : "rgba(255, 255, 255, 0.98)",
                    borderWidth: 3,
                    shadowBlur: 12,
                    shadowColor: "rgba(245, 158, 11, 0.45)",
                  },
                }
              : row.wr_gap,
          ),
        },
      ],
    }

    chart.setOption(option, {
      notMerge: true,
    })
  }, [
    chartRows,
    currentPbUuid,
    deltaByUuid,
    formatDateTime,
    resolvedTheme,
    wrTime,
  ])

  useEffect(() => {
    const chart = chartInstanceRef.current
    if (!chart) {
      return
    }

    const handleAxisPointerUpdate = (event: unknown) => {
      const pointerEvent = event as {
        axesInfo?: Array<{ axisDim?: string; value?: string | number }>
      }
      const xAxisInfo = pointerEvent.axesInfo?.find(
        (axisInfo) => axisInfo.axisDim === "x",
      )
      const dataIndex = getAxisPointerDataIndex(xAxisInfo?.value, chartRows)
      onHighlightedUuidChange(chartRows[dataIndex]?.uuid ?? null)
    }
    const handleGlobalOut = () => {
      onHighlightedUuidChange(null)
    }

    chart.on("updateAxisPointer", handleAxisPointerUpdate)
    chart.on("globalout", handleGlobalOut)

    return () => {
      chart.off("updateAxisPointer", handleAxisPointerUpdate)
      chart.off("globalout", handleGlobalOut)
    }
  }, [chartRows, onHighlightedUuidChange])

  useEffect(() => {
    const chart = chartInstanceRef.current
    if (!chart) {
      return
    }

    chart.dispatchAction({
      type: "downplay",
      seriesIndex: 0,
    })

    const dataIndex = chartRows.findIndex((row) => row.uuid === highlightedUuid)
    if (dataIndex === -1) {
      chart.dispatchAction({
        type: "hideTip",
      })
      return
    }

    chart.dispatchAction({
      type: "highlight",
      seriesIndex: 0,
      dataIndex,
    })
    chart.dispatchAction({
      type: "showTip",
      seriesIndex: 0,
      dataIndex,
    })
  }, [chartRows, highlightedUuid])

  if (!hasChartData) {
    return (
      <div className="flex h-72 items-center justify-center rounded-lg border border-dashed border-border/70 bg-muted/20 text-sm text-muted-foreground">
        No finite run-time points for this view.
      </div>
    )
  }

  return (
    <div
      ref={chartRef}
      className="h-72 w-full"
      data-testid="record-run-history-chart"
      role="img"
      aria-label="Run history line chart"
    />
  )
}

function HistoryRows({
  currentPbUuid,
  deltaByUuid,
  highlightedUuid,
  onHighlightedUuidChange,
  rows,
}: {
  currentPbUuid: string | null
  deltaByUuid: Map<string, number>
  highlightedUuid: string | null
  onHighlightedUuidChange: (uuid: string | null) => void
  rows: RecordRunHistoryEntryPublic[]
}) {
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>())
  const sortedRows = useMemo(
    () =>
      [...rows].sort((left, right) => {
        const dateComparison =
          Date.parse(right.created_on) - Date.parse(left.created_on)
        if (dateComparison !== 0) {
          return dateComparison
        }
        return left.time - right.time
      }),
    [rows],
  )

  useEffect(() => {
    if (!highlightedUuid) {
      return
    }

    rowRefs.current.get(highlightedUuid)?.scrollIntoView({
      block: "nearest",
      behavior: "smooth",
    })
  }, [highlightedUuid])

  return (
    <div className="max-h-52 overflow-y-auto rounded-lg border border-border/70">
      <table className="w-full table-fixed border-collapse">
        <tbody>
          {sortedRows.map((row) => (
            <tr
              key={row.uuid}
              ref={(element) => {
                if (element) {
                  rowRefs.current.set(row.uuid, element)
                  return
                }
                rowRefs.current.delete(row.uuid)
              }}
              className={cn(
                "border-b border-border/60 text-sm transition-colors last:border-b-0",
                currentPbUuid === row.uuid &&
                  "bg-amber-500/10 ring-1 ring-inset ring-amber-500/30",
                highlightedUuid === row.uuid &&
                  "bg-primary/8 ring-1 ring-inset ring-primary/25",
              )}
              onMouseEnter={() => onHighlightedUuidChange(row.uuid)}
              onMouseLeave={() => onHighlightedUuidChange(null)}
            >
              <td className="min-w-0 px-3 py-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="font-mono font-medium">
                    {formatRecordTime(row.time)}
                  </span>
                  {deltaByUuid.has(row.uuid) ? (
                    <span
                      className={cn(
                        "font-mono text-xs font-semibold",
                        (deltaByUuid.get(row.uuid) ?? 0) < 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-red-600 dark:text-red-400",
                      )}
                    >
                      {getRunTimeDeltaLabel(deltaByUuid.get(row.uuid) ?? 0)}
                    </span>
                  ) : null}
                  {row.is_pb ? (
                    <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                      {row.uuid === currentPbUuid ? "Current PB" : "PB"}
                    </span>
                  ) : null}
                  <span className="truncate text-xs text-muted-foreground">
                    {row.mode} · {row.teleports} TP
                  </span>
                </div>
              </td>
              <td className="w-64 px-3 py-2 text-right text-xs text-muted-foreground">
                <span>{row.server_name} · </span>
                <FormattedDateTime value={row.created_on} fallback="-" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function RecordRunHistoryDialog({
  identifier,
  initialType,
  onOpenChange,
  open,
  record,
  scope,
}: {
  identifier: string
  initialType: RunHistoryRecordType
  onOpenChange: (open: boolean) => void
  open: boolean
  record: RecordPublic | null
  scope: AppScope
}) {
  const [recordType, setRecordType] =
    useState<RunHistoryRecordType>(initialType)
  const [showPbOnly, setShowPbOnly] = useState(false)
  const [showBestPerDayOnly, setShowBestPerDayOnly] = useState(false)
  const [highlightedUuid, setHighlightedUuid] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    setRecordType(initialType)
    setShowPbOnly(false)
    setShowBestPerDayOnly(false)
    setHighlightedUuid(null)
  }, [initialType, open])

  const historyQuery = useQuery({
    ...getRecordRunHistoryQueryOptions({
      identifier,
      mapId: record?.map_id ?? null,
      stage: record?.stage ?? 0,
      scope,
      type: recordType,
      enabled: open && record !== null,
    }),
  })
  const rows = historyQuery.data?.data ?? []
  const filteredRows = showPbOnly ? rows.filter((row) => row.is_pb) : rows
  const previousPbDeltaByUuid = useMemo(
    () => getPreviousPbDeltaByUuid(filteredRows),
    [filteredRows],
  )
  const currentPbRun = useMemo(
    () => getCurrentPbRun(filteredRows),
    [filteredRows],
  )
  const visibleRows = showBestPerDayOnly
    ? collapseRunsToBestPerDay(filteredRows)
    : filteredRows
  const title = record ? `${record.map_name} Run History` : "Run History"

  useEffect(() => {
    if (
      highlightedUuid &&
      !visibleRows.some((row) => row.uuid === highlightedUuid)
    ) {
      setHighlightedUuid(null)
    }
  }, [highlightedUuid, visibleRows])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[88vh] overflow-y-auto sm:max-w-4xl"
        data-testid="record-run-history-dialog"
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Tabs
            value={showPbOnly ? "pb" : "all"}
            onValueChange={(value) => setShowPbOnly(value === "pb")}
          >
            <TabsList>
              <TabsTrigger value="pb">PB Runs</TabsTrigger>
              <TabsTrigger value="all">All Runs</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex flex-wrap items-center gap-2">
            <Label
              htmlFor="record-run-history-best-per-day"
              className="flex h-9 w-fit items-center justify-start gap-2 rounded-lg border border-border/70 bg-background/80 px-3 text-[11px] font-medium tracking-[0.08em] text-foreground/80 uppercase"
            >
              <Switch
                id="record-run-history-best-per-day"
                checked={showBestPerDayOnly}
                onCheckedChange={setShowBestPerDayOnly}
              />
              <span>Best/day</span>
            </Label>
            <Label
              htmlFor="record-run-history-pro-only"
              className="flex h-9 w-fit items-center justify-start gap-2 rounded-lg border border-border/70 bg-background/80 px-3 text-[11px] font-medium tracking-[0.08em] text-foreground/80 uppercase"
            >
              <Switch
                id="record-run-history-pro-only"
                checked={recordType === "PRO"}
                onCheckedChange={(checked) => {
                  setRecordType(checked ? "PRO" : "NUB")
                }}
                className="data-[state=unchecked]:bg-[#f3c40f] data-[state=unchecked]:shadow-[#f3c40f]/35 data-[state=checked]:bg-[#3598db] data-[state=checked]:shadow-[#3598db]/35 dark:data-[state=checked]:bg-[#3598db]"
              />
              <span>{recordType}</span>
            </Label>
          </div>
        </div>

        {currentPbRun ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded-md bg-amber-500/10 px-2 py-1 text-[11px] font-semibold tracking-[0.08em] text-amber-700 uppercase dark:text-amber-300">
              Current PB
            </span>
            <span className="font-mono font-semibold">
              {formatRecordTime(currentPbRun.time)}
            </span>
          </div>
        ) : null}

        {historyQuery.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-72 w-full rounded-lg" />
            <Skeleton className="h-28 w-full rounded-lg" />
          </div>
        ) : historyQuery.isError ? (
          <div className="rounded-lg border border-dashed border-destructive/40 bg-destructive/5 px-4 py-8 text-sm text-muted-foreground">
            Failed to load run history.
          </div>
        ) : visibleRows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/70 bg-muted/20 px-4 py-10 text-center text-sm text-muted-foreground">
            <div className="mx-auto mb-3 flex size-10 items-center justify-center rounded-full border border-border/70 bg-background/80">
              <LineChart className="size-4" />
            </div>
            No runs found for this view.
          </div>
        ) : (
          <div className="space-y-4">
            <RunHistoryChart
              currentPbUuid={currentPbRun?.uuid ?? null}
              deltaByUuid={previousPbDeltaByUuid}
              highlightedUuid={highlightedUuid}
              onHighlightedUuidChange={setHighlightedUuid}
              rows={visibleRows}
              wrTime={historyQuery.data?.wr_time}
            />
            <HistoryRows
              currentPbUuid={currentPbRun?.uuid ?? null}
              deltaByUuid={previousPbDeltaByUuid}
              highlightedUuid={highlightedUuid}
              onHighlightedUuidChange={setHighlightedUuid}
              rows={visibleRows}
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
