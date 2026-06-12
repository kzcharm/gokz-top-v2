import type { EChartsOption } from "echarts"
import * as echarts from "echarts"
import { CheckCircle2, PinOff } from "lucide-react"
import type { KeyboardEvent, MouseEvent, ReactNode } from "react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import type { PlayerDailyActivityPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PointsBadge } from "@/components/Records/PointsBadge"
import { formatCompactCount } from "@/components/Records/TeleportsBadge"
import { formatRecordTime } from "@/components/Records/utils"
import { useTheme } from "@/components/theme-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useHorizontalDragScroll } from "@/hooks/useHorizontalDragScroll"
import { useMediaQuery } from "@/hooks/useMobile"
import { getLocale } from "@/i18n/locale"
import { cn } from "@/lib/utils"
import { ProfileDurationControls } from "./ProfileDurationControls"
import type { ProfileRecordDistributionBin } from "./profile-record-distribution"
import {
  formatNumber,
  type ProfileCompletionData,
  type ProfilePinnedRecord,
  type ProfileTrophyCounts,
} from "./profile-utils"

const activityToneClasses = [
  "bg-[#ebedf0] dark:bg-[#161b22]",
  "bg-[#9be9a8] dark:bg-[#0e4429]",
  "bg-[#40c463] dark:bg-[#006d32]",
  "bg-[#30a14e] dark:bg-[#26a641]",
  "bg-[#216e39] dark:bg-[#39d353]",
]

const TROPHY_ASSETS = {
  gold: "https://kzgo.eu/trophy4.png",
  silver: "https://kzgo.eu/trophy_silver2.png",
  bronze: "https://kzgo.eu/trophy_bronze.png",
} as const
const PROFILE_COMPLETION_TWO_COLUMN_MIN_WIDTH = 960
const ROLLING_ACTIVITY_WINDOW_ID = "last-365-days"
const PROFILE_DISTRIBUTION_TWO_COLUMN_MIN_WIDTH = 1080
const ACTIVITY_WEEK_WIDTH_PX = 13
const ACTIVITY_MONTH_LABEL_MIN_WEEK_GAP = 3

type ActivityCell = {
  date: string
  count: number
  isEmpty: boolean
  level: number
}

type ActivityMonthLabel = {
  month: string
  weekIndex: number
}

function PaddedAverageNumber({ value }: { value: number }) {
  const formattedValue = String(value)
  const paddedValue = formattedValue.padStart(3, "0")

  return <span className="font-mono tabular-nums">{paddedValue}</span>
}

function CompletionCard({
  title,
  completed,
  total,
  tiers,
  trophies,
}: {
  title: string
  completed: number
  total: number
  tiers: Array<{
    label: string
    complete: number
    total: number
    color: string
    averagePoints: number
  }>
  trophies: ProfileTrophyCounts
}) {
  const { t } = useTranslation()
  return (
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="p-6">
        <div className="mx-auto w-full max-w-[36rem] space-y-5">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                {title}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-4">
                {(["gold", "silver", "bronze"] as const).map((trophy) => (
                  <div key={trophy} className="flex items-center gap-2">
                    <img
                      src={TROPHY_ASSETS[trophy]}
                      alt={t("profile.completion.trophyAlt", {
                        trophy: t(`profile.completion.trophies.${trophy}`),
                      })}
                      className="h-7 w-7 object-contain"
                    />
                    <span className="text-2xl font-semibold tracking-tight">
                      {formatNumber(trophies[trophy])}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <p className="text-sm text-muted-foreground md:justify-self-end">
              {formatNumber(completed)} / {formatNumber(total)}
            </p>
          </div>
          <div className="space-y-1.5">
            {tiers.map((tier) => {
              const width = `${tier.total === 0 ? 0 : (tier.complete / tier.total) * 100}%`
              const isTierComplete =
                tier.total > 0 && tier.complete >= tier.total
              return (
                <div
                  key={tier.label}
                  className="grid grid-cols-[88px_minmax(0,1fr)_auto] items-center gap-2 sm:grid-cols-[96px_minmax(0,1fr)_58px] sm:gap-3"
                >
                  <span className="whitespace-nowrap text-right text-[11px] font-semibold leading-4 text-muted-foreground sm:text-xs">
                    {tier.label} ({t("profile.completion.averageShort")}{" "}
                    <PaddedAverageNumber value={tier.averagePoints} />)
                  </span>
                  <div className="h-5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full"
                      style={{ width, backgroundColor: tier.color }}
                    />
                  </div>
                  <span className="flex items-center justify-end gap-1 text-right font-mono text-[11px] tabular-nums text-muted-foreground sm:justify-start sm:text-left sm:text-xs">
                    {tier.complete}/{tier.total}
                    {isTierComplete ? (
                      <CheckCircle2
                        aria-hidden="true"
                        className="size-3 shrink-0"
                        style={{ color: "#22C55E" }}
                      />
                    ) : null}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function CompletionCardsSkeleton({ twoColumns }: { twoColumns: boolean }) {
  return (
    <div className={cn("grid gap-6", twoColumns && "lg:grid-cols-2")}>
      {Array.from({ length: 2 }, (_, index) => (
        <Card
          key={index}
          className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0"
        >
          <CardContent className="p-6">
            <div className="mx-auto w-full max-w-[28rem] space-y-5">
              <div className="flex items-end justify-between gap-4">
                <div className="space-y-3">
                  <Skeleton className="h-4 w-36" />
                  <Skeleton className="h-9 w-24" />
                </div>
                <Skeleton className="h-5 w-20" />
              </div>
              <div className="space-y-2">
                {Array.from({ length: 8 }, (_, tierIndex) => (
                  <Skeleton key={tierIndex} className="h-5 w-full" />
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function getCurrentUtcYear() {
  return String(new Date().getUTCFullYear())
}

function getCurrentUtcDate() {
  const now = new Date()
  return new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
  )
}

function getWeekdayLabels(locale: string) {
  const formatter = new Intl.DateTimeFormat(locale, {
    weekday: "short",
    timeZone: "UTC",
  })

  return Array.from({ length: 7 }, (_, index) =>
    formatter.format(new Date(Date.UTC(2026, 0, 4 + index))),
  )
}

function formatActivityDate(date: string, locale: string) {
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${date}T00:00:00Z`))
}

function getActivityLevel(count: number) {
  if (count <= 0) {
    return 0
  }

  if (count >= 10) {
    return 4
  }

  if (count >= 5) {
    return 3
  }

  if (count >= 2) {
    return 2
  }

  return 1
}

function buildActivityCalendar({
  days,
  start,
  end,
  locale,
}: {
  days: Array<{ date: string; count: number }>
  start: Date
  end: Date
  locale: string
}) {
  const startDate = new Date(start)
  const endDate = new Date(end)
  const monthFormatter = new Intl.DateTimeFormat(locale, {
    month: "short",
    timeZone: "UTC",
  })
  const countsByDate = new Map(
    days
      .filter((day) => {
        const date = new Date(`${day.date}T00:00:00Z`)
        return date >= startDate && date <= endDate
      })
      .map((day) => [day.date, day.count]),
  )
  const weeks: ActivityCell[][] = []
  let currentWeek: ActivityCell[] = []
  const current = new Date(startDate)
  const startDayOfWeek = current.getUTCDay()
  const rangeKey = `${startDate.toISOString().slice(0, 10)}-${endDate.toISOString().slice(0, 10)}`

  for (let dayIndex = 0; dayIndex < startDayOfWeek; dayIndex += 1) {
    currentWeek.push({
      date: `${rangeKey}-empty-0-${dayIndex}`,
      count: 0,
      isEmpty: true,
      level: 0,
    })
  }

  while (current <= endDate) {
    const date = current.toISOString().slice(0, 10)
    const count = countsByDate.get(date) ?? 0

    currentWeek.push({
      date,
      count,
      isEmpty: false,
      level: getActivityLevel(count),
    })

    if (current.getUTCDay() === 6) {
      weeks.push(currentWeek)
      currentWeek = []
    }

    current.setUTCDate(current.getUTCDate() + 1)
  }

  if (currentWeek.length > 0) {
    while (currentWeek.length < 7) {
      currentWeek.push({
        date: `${rangeKey}-empty-${weeks.length}-${currentWeek.length}`,
        count: 0,
        isEmpty: true,
        level: 0,
      })
    }

    weeks.push(currentWeek)
  }

  const monthLabels: ActivityMonthLabel[] = []
  let lastMonth = -1

  for (const [weekIndex, week] of weeks.entries()) {
    const firstRealDay = week.find((day) => !day.isEmpty)
    if (!firstRealDay) {
      continue
    }

    const monthIndex = new Date(`${firstRealDay.date}T00:00:00Z`).getUTCMonth()
    if (monthIndex !== lastMonth) {
      monthLabels.push({
        month: monthFormatter.format(new Date(Date.UTC(2026, monthIndex, 1))),
        weekIndex,
      })
      lastMonth = monthIndex
    }
  }

  const spacedMonthLabels = monthLabels.reduce<ActivityMonthLabel[]>(
    (labels, label) => {
      const previousLabel = labels[labels.length - 1]
      if (
        previousLabel &&
        label.weekIndex - previousLabel.weekIndex <
          ACTIVITY_MONTH_LABEL_MIN_WEEK_GAP
      ) {
        if (previousLabel.weekIndex === 0) {
          labels[labels.length - 1] = label
        }

        return labels
      }

      labels.push(label)
      return labels
    },
    [],
  )

  return {
    monthLabels: spacedMonthLabels,
    weeks,
    hasActivity: Array.from(countsByDate.values()).some((count) => count > 0),
  }
}

function ActivityCard({
  activityError,
  activityLoading,
  activityStat,
}: {
  activityError: boolean
  activityLoading: boolean
  activityStat: PlayerDailyActivityPublic | null
}) {
  const { t, i18n } = useTranslation()
  const activityScrollRef = useHorizontalDragScroll<HTMLDivElement>()
  const allDays = activityStat?.days ?? []
  const fallbackYear = getCurrentUtcYear()
  const locale = i18n.resolvedLanguage ?? i18n.language ?? getLocale()
  const weekdayLabels = useMemo(() => getWeekdayLabels(locale), [locale])
  const yearViewIds = useMemo(() => {
    const years = Array.from(
      new Set(allDays.map((day) => day.date.slice(0, 4))),
    )
    years.sort((left, right) => Number(left) - Number(right))
    return years.length > 0 ? years : [fallbackYear]
  }, [allDays, fallbackYear])
  const defaultYearId = yearViewIds[yearViewIds.length - 1] ?? fallbackYear
  const [activeView, setActiveView] = useState(ROLLING_ACTIVITY_WINDOW_ID)

  useEffect(() => {
    const allowedViews = new Set([ROLLING_ACTIVITY_WINDOW_ID, ...yearViewIds])
    setActiveView((currentView) =>
      allowedViews.has(currentView) ? currentView : ROLLING_ACTIVITY_WINDOW_ID,
    )
  }, [yearViewIds])

  const { hasActivity, monthLabels, weeks, emptyStateLabel, rangeKey } =
    useMemo(() => {
      if (activeView === ROLLING_ACTIVITY_WINDOW_ID) {
        const end = getCurrentUtcDate()
        const start = new Date(end)
        start.setUTCDate(start.getUTCDate() - 364)

        return {
          ...buildActivityCalendar({
            days: allDays,
            start,
            end,
            locale,
          }),
          emptyStateLabel: t("profile.activity.latestRange"),
          rangeKey: ROLLING_ACTIVITY_WINDOW_ID,
        }
      }

      const selectedYear = Number(activeView)
      const start = new Date(Date.UTC(selectedYear, 0, 1))
      const end = new Date(Date.UTC(selectedYear, 11, 31))

      return {
        ...buildActivityCalendar({
          days: allDays,
          start,
          end,
          locale,
        }),
        emptyStateLabel: activeView,
        rangeKey: activeView,
      }
    }, [activeView, allDays, locale, t])

  if (activityLoading) {
    return (
      <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
        <CardContent className="space-y-5 p-6">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                {t("profile.activity.title")}
              </p>
              <Skeleton className="h-4 w-40" />
            </div>
            <Skeleton className="h-10 w-28 rounded-full" />
          </div>
          <Skeleton className="h-28 w-full rounded-[18px]" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              {t("profile.activity.title")}
            </p>
          </div>
          <ProfileDurationControls
            activeViewId={activeView}
            defaultYearId={defaultYearId}
            onActiveViewIdChange={setActiveView}
            onPlayingChange={() => {}}
            specialViews={[
              {
                id: ROLLING_ACTIVITY_WINDOW_ID,
                label: t("profile.activity.latest"),
                testId: `profile-activity-view-${ROLLING_ACTIVITY_WINDOW_ID}`,
              },
            ]}
            testIdPrefix="profile-activity"
            yearIds={yearViewIds}
          />
        </div>

        {activityError ? (
          <p className="text-sm text-destructive">
            {t("profile.activity.loadFailed")}
          </p>
        ) : null}

        <div ref={activityScrollRef} className="overflow-x-auto">
          <div className="flex w-full justify-center">
            <div className="min-w-fit">
              <div
                className="relative ml-8 h-4"
                style={{ width: `${weeks.length * ACTIVITY_WEEK_WIDTH_PX}px` }}
              >
                {monthLabels.map((label) => (
                  <span
                    key={`${rangeKey}-${label.month}-${label.weekIndex}`}
                    data-testid={`profile-activity-month-${label.month}`}
                    className="absolute top-0 text-[11px] leading-4 text-muted-foreground"
                    style={{
                      left: `${label.weekIndex * ACTIVITY_WEEK_WIDTH_PX}px`,
                    }}
                  >
                    {label.month}
                  </span>
                ))}
              </div>

              <div className="mt-2 flex gap-2">
                <div className="flex flex-col justify-around pt-px text-[11px] leading-[10px] text-muted-foreground">
                  {[1, 3, 5].map((dayIndex) => (
                    <span key={weekdayLabels[dayIndex]} className="h-[23px]">
                      {weekdayLabels[dayIndex]}
                    </span>
                  ))}
                </div>

                <div className="flex gap-[3px]">
                  {weeks.map((week, weekIndex) => (
                    <div
                      key={`${rangeKey}-week-${weekIndex}`}
                      className="flex flex-col gap-[3px]"
                    >
                      {week.map((day, dayIndex) =>
                        day.isEmpty ? (
                          <span
                            key={`${weekIndex}-${dayIndex}-${day.date}`}
                            data-testid={`profile-activity-cell-${day.date}`}
                            data-activity-level="0"
                            className="h-2.5 w-2.5 shrink-0"
                          />
                        ) : (
                          <Tooltip
                            key={`${weekIndex}-${dayIndex}-${day.date}`}
                            delayDuration={0}
                          >
                            <TooltipTrigger asChild>
                              <span
                                data-testid={`profile-activity-cell-${day.date}`}
                                data-activity-level={day.level}
                                className={cn(
                                  "h-2.5 w-2.5 shrink-0 rounded-[2px] border border-[rgba(27,31,35,0.06)] transition-colors hover:border-muted-foreground/45 dark:border-[#1b1f23] dark:hover:border-muted-foreground/55",
                                  activityToneClasses[day.level],
                                )}
                              />
                            </TooltipTrigger>
                            <TooltipContent
                              hideArrow
                              sideOffset={6}
                              className="rounded-sm border border-border bg-background px-2 py-1 font-normal text-foreground shadow-md"
                            >
                              {t("profile.activity.cellTooltip", {
                                count: day.count,
                                date: formatActivityDate(day.date, locale),
                              })}
                            </TooltipContent>
                          </Tooltip>
                        ),
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {!activityError && !hasActivity ? (
          <p className="text-sm text-muted-foreground">
            {t("profile.activity.emptyState", { range: emptyStateLabel })}
          </p>
        ) : null}

        <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <span>{t("profile.activity.less")}</span>
          {activityToneClasses.map((tone, index) => (
            <span
              key={index}
              className={cn(
                "h-2.5 w-2.5 rounded-[2px] border border-[rgba(27,31,35,0.06)] dark:border-[#1b1f23]",
                tone,
              )}
            />
          ))}
          <span>{t("profile.activity.more")}</span>
        </div>
      </CardContent>
    </Card>
  )
}

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

function RecordDistributionSection({
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

function PinnedRecordsCard({
  canManagePinnedRecords,
  pinnedRecords,
  loading,
  mutating,
  onUnpinRecord,
}: {
  canManagePinnedRecords: boolean
  pinnedRecords: ProfilePinnedRecord[]
  loading: boolean
  mutating: boolean
  onUnpinRecord: (mapId: number, type: "NUB" | "PRO") => void
}) {
  const { t } = useTranslation()
  return (
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              {t("profile.pinned.title")}
            </p>
          </div>
          <p className="text-sm text-muted-foreground">
            {t("profile.pinned.count", { count: pinnedRecords.length })}
          </p>
        </div>

        {loading ? (
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {Array.from({ length: 6 }, (_, index) => (
              <Skeleton key={index} className="h-32 rounded-[22px]" />
            ))}
          </div>
        ) : pinnedRecords.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {pinnedRecords.map(({ mapId, record, rank, totalCount, type }) => {
              const content = (
                <div className="group rounded-[22px] border border-border/70 bg-background/75 p-4 transition-colors hover:border-primary/35">
                  <p className="truncate text-sm font-semibold">
                    {record.map_name}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {record.mode} ·{" "}
                    {rank === null
                      ? t("profile.pinned.rankUnavailable")
                      : totalCount === null
                        ? `#${formatNumber(rank)}`
                        : `#${formatNumber(rank)} / ${formatCompactCount(totalCount)}`}
                  </p>
                  <p className="mt-4 text-2xl font-semibold tracking-tight text-primary">
                    {formatRecordTime(record.time)}
                  </p>
                  <div className="mt-3 flex items-center gap-2">
                    <PointsBadge points={record.points} />
                    <span className="text-xs text-muted-foreground">
                      <FormattedDateTime
                        value={record.created_on}
                        display="absolute"
                        fallback="-"
                      />
                    </span>
                  </div>
                </div>
              )

              if (!canManagePinnedRecords) {
                return <div key={record.uuid}>{content}</div>
              }

              return (
                <ManagedPinnedRecordCard
                  key={record.uuid}
                  disabled={mutating}
                  onUnpin={() => onUnpinRecord(mapId, type)}
                >
                  {content}
                </ManagedPinnedRecordCard>
              )
            })}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {t("profile.pinned.empty")}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function ManagedPinnedRecordCard({
  children,
  disabled,
  onUnpin,
}: {
  children: ReactNode
  disabled: boolean
  onUnpin: () => void
}) {
  const { t } = useTranslation()
  const [menuOpen, setMenuOpen] = useState(false)
  const contextMenuRequestedRef = useRef(false)

  return (
    <DropdownMenu
      modal={false}
      open={menuOpen}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          contextMenuRequestedRef.current = false
          setMenuOpen(false)
          return
        }

        if (contextMenuRequestedRef.current) {
          setMenuOpen(true)
        }
      }}
    >
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-haspopup="menu"
          aria-disabled={disabled}
          className="block w-full text-left"
          onContextMenu={(event: MouseEvent<HTMLButtonElement>) => {
            event.preventDefault()
            contextMenuRequestedRef.current = true
            setMenuOpen(true)
          }}
          onKeyDown={(event: KeyboardEvent<HTMLButtonElement>) => {
            if (
              event.key === "ContextMenu" ||
              (event.shiftKey && event.key === "F10")
            ) {
              event.preventDefault()
              contextMenuRequestedRef.current = true
              setMenuOpen(true)
            }
          }}
        >
          {children}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="bottom" sideOffset={8}>
        <DropdownMenuItem
          disabled={disabled}
          onSelect={(event) => {
            event.preventDefault()
            onUnpin()
          }}
        >
          <PinOff />
          {t("profile.pinned.unpin")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function ProfileHomeContent({
  activityError,
  activityLoading,
  activityStat,
  canManagePinnedRecords,
  nubRecordDistribution,
  pinnedRecords,
  pinnedRecordsError,
  pinnedRecordsLoading,
  pinnedRecordsMutating,
  proRecordDistribution,
  recordDistributionError,
  recordDistributionLoading,
  onUnpinRecord,
}: {
  activityError: boolean
  activityLoading: boolean
  activityStat: PlayerDailyActivityPublic | null
  nubRecordDistribution: ProfileRecordDistributionBin[]
  pinnedRecords: ProfilePinnedRecord[]
  pinnedRecordsError: boolean
  pinnedRecordsLoading: boolean
  pinnedRecordsMutating: boolean
  proRecordDistribution: ProfileRecordDistributionBin[]
  recordDistributionError: boolean
  recordDistributionLoading: boolean
  onUnpinRecord: (mapId: number, type: "NUB" | "PRO") => void
  canManagePinnedRecords: boolean
}) {
  const { t } = useTranslation()
  return (
    <div className="min-w-0 space-y-6">
      <ActivityCard
        activityError={activityError}
        activityLoading={activityLoading}
        activityStat={activityStat}
      />
      <RecordDistributionSection
        nubRecordDistribution={nubRecordDistribution}
        proRecordDistribution={proRecordDistribution}
        recordDistributionError={recordDistributionError}
        recordDistributionLoading={recordDistributionLoading}
      />
      {pinnedRecordsError ? (
        <Alert variant="destructive">
          <AlertTitle>{t("profile.pinned.loadFailedTitle")}</AlertTitle>
          <AlertDescription>
            {t("profile.pinned.loadFailedBody")}
          </AlertDescription>
        </Alert>
      ) : null}
      <PinnedRecordsCard
        canManagePinnedRecords={canManagePinnedRecords}
        pinnedRecords={pinnedRecords}
        loading={pinnedRecordsLoading}
        mutating={pinnedRecordsMutating}
        onUnpinRecord={onUnpinRecord}
      />
    </div>
  )
}

export function ProfileCompletionSection({
  completion,
  completionLoading,
  completionError,
  completionTrophies,
}: {
  completion: ProfileCompletionData
  completionLoading: boolean
  completionError: boolean
  completionTrophies: {
    nub: ProfileTrophyCounts
    pro: ProfileTrophyCounts
  }
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

  const showCompletionCardsInTwoColumns =
    contentWidth >= PROFILE_COMPLETION_TWO_COLUMN_MIN_WIDTH

  return (
    <div ref={contentRef} className="min-w-0 space-y-6">
      {completionError ? (
        <Alert variant="destructive">
          <AlertTitle>{t("profile.completion.loadFailedTitle")}</AlertTitle>
          <AlertDescription>
            {t("profile.completion.loadFailedBody")}
          </AlertDescription>
        </Alert>
      ) : completionLoading ? (
        <CompletionCardsSkeleton twoColumns={showCompletionCardsInTwoColumns} />
      ) : (
        <div
          className={cn(
            "grid gap-6",
            showCompletionCardsInTwoColumns && "lg:grid-cols-2",
          )}
        >
          <CompletionCard
            title={t("profile.completion.nubTitle")}
            completed={completion.nub.completed}
            total={completion.nub.total}
            tiers={completion.nub.tiers}
            trophies={completionTrophies.nub}
          />
          <CompletionCard
            title={t("profile.completion.proTitle")}
            completed={completion.pro.completed}
            total={completion.pro.total}
            tiers={completion.pro.tiers}
            trophies={completionTrophies.pro}
          />
        </div>
      )}
    </div>
  )
}
