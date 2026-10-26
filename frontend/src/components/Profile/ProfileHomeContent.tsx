import { Link } from "@tanstack/react-router"
import { PinOff } from "lucide-react"
import type { ComponentPropsWithRef, KeyboardEvent, MouseEvent } from "react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import type { PlayerDailyActivityPublic } from "@/client"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import { ProfileSetupCard } from "@/components/Gear/ProfileSetupCard"
import { PointsBadge } from "@/components/Records/PointsBadge"
import { StageBadge } from "@/components/Records/StageBadge"
import { formatCompactCount } from "@/components/Records/TeleportsBadge"
import { formatRecordTime } from "@/components/Records/utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useHorizontalDragScroll } from "@/hooks/useHorizontalDragScroll"
import { useMapImageUrls } from "@/hooks/useMapImageUrls"
import { getLocale } from "@/i18n/locale"
import { cn } from "@/lib/utils"
import { CompletionCard } from "./ProfileCompletionCard"
import { ProfileDurationControls } from "./ProfileDurationControls"
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

const PROFILE_COMPLETION_TWO_COLUMN_MIN_WIDTH = 960
const ROLLING_ACTIVITY_WINDOW_ID = "last-365-days"
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
    totalDays:
      Math.round((endDate.getTime() - startDate.getTime()) / 86_400_000) + 1,
    monthLabels: spacedMonthLabels,
    weeks,
    daysPlayed: Array.from(countsByDate.values()).filter((count) => count > 0)
      .length,
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
  const { formatDateTime } = useDateTimeFormat()
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
  const lastCalendarYearRef = useRef(defaultYearId)
  const isRollingActivity = activeView === ROLLING_ACTIVITY_WINDOW_ID
  const activityMode = isRollingActivity ? "rolling" : "calendar"
  const selectCalendarYear = (year: string) => {
    lastCalendarYearRef.current = year
    setActiveView(year)
  }

  useEffect(() => {
    const allowedViews = new Set([ROLLING_ACTIVITY_WINDOW_ID, ...yearViewIds])
    setActiveView((currentView) =>
      allowedViews.has(currentView) ? currentView : ROLLING_ACTIVITY_WINDOW_ID,
    )
  }, [yearViewIds])

  const {
    daysPlayed,
    totalDays,
    monthLabels,
    weeks,
    emptyStateLabel,
    rangeKey,
  } = useMemo(() => {
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
      <CardContent className="p-6">
        <Tabs
          value={activityMode}
          onValueChange={(mode) => {
            if (mode === "rolling") {
              setActiveView(ROLLING_ACTIVITY_WINDOW_ID)
            } else {
              selectCalendarYear(
                yearViewIds.includes(lastCalendarYearRef.current)
                  ? lastCalendarYearRef.current
                  : defaultYearId,
              )
            }
          }}
          className="gap-5"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              {t("profile.activity.title")}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <div hidden={isRollingActivity}>
                <ProfileDurationControls
                  activeViewId={activeView}
                  defaultYearId={defaultYearId}
                  onActiveViewIdChange={selectCalendarYear}
                  onPlayingChange={() => {}}
                  specialViews={[]}
                  testIdPrefix="profile-activity"
                  yearIds={yearViewIds}
                />
              </div>
              <TabsList aria-label={t("profile.activity.title")}>
                <TabsTrigger
                  value="calendar"
                  data-testid="profile-activity-view-calendar-year"
                >
                  {t("profile.activity.calendarYear")}
                </TabsTrigger>
                <TabsTrigger
                  value="rolling"
                  data-testid={`profile-activity-view-${ROLLING_ACTIVITY_WINDOW_ID}`}
                >
                  {t("profile.activity.latest")}
                </TabsTrigger>
              </TabsList>
            </div>
          </div>

          <TabsContent value={activityMode} className="flex flex-col gap-5">
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
                    style={{
                      width: `${weeks.length * ACTIVITY_WEEK_WIDTH_PX}px`,
                    }}
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
                        <span
                          key={weekdayLabels[dayIndex]}
                          className="h-[23px]"
                        >
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
                                    // Keep this UTC activity bucket's calendar date
                                    // when formatting in the browser's time zone.
                                    date: formatDateTime(
                                      `${day.date}T00:00:00`,
                                      {
                                        dateOnly: true,
                                        locale,
                                      },
                                    ),
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

            {!activityError && daysPlayed === 0 ? (
              <p className="text-sm text-muted-foreground">
                {t("profile.activity.emptyState", { range: emptyStateLabel })}
              </p>
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-3">
              {!activityError ? (
                <span
                  className="text-sm tabular-nums text-muted-foreground"
                  data-testid="profile-activity-days-played"
                >
                  {t("profile.activity.daysPlayed", {
                    count: daysPlayed,
                    percentage: new Intl.NumberFormat(locale, {
                      style: "percent",
                      minimumFractionDigits: 1,
                      maximumFractionDigits: 1,
                    }).format(daysPlayed / totalDays),
                  })}
                </span>
              ) : null}
              <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
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
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}

function PinnedRecordCard({
  record,
  rank,
  totalCount,
  ...linkProps
}: Pick<ProfilePinnedRecord, "record" | "rank" | "totalCount"> &
  Omit<ComponentPropsWithRef<"a">, "children">) {
  const { t } = useTranslation()
  const { formatDateTime } = useDateTimeFormat()
  const imageUrls = useMapImageUrls(record.map_name)

  return (
    <Link
      {...linkProps}
      to="/maps/$mapName/maptop"
      params={{ mapName: record.map_name }}
      data-testid="pinned-record-card"
      className="group relative isolate flex min-h-[76px] min-w-0 items-center gap-3 overflow-hidden rounded-[14px] border border-white/10 bg-slate-900 px-3.5 py-3 text-white [text-shadow:0_1px_3px_rgb(0_0_0/0.6)] transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-20 bg-cover bg-center brightness-110 transition-transform dark:brightness-100 duration-300 group-hover:scale-105 motion-reduce:transition-none motion-reduce:group-hover:scale-100"
        style={{
          backgroundImage: imageUrls
            .map((url) => `url("${url.replace(/"/g, "%22")}")`)
            .join(", "),
        }}
      />
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 bg-gradient-to-r from-slate-950/70 via-slate-950/15 to-slate-950/65 dark:from-slate-950/85 dark:via-slate-950/65 dark:to-slate-950/75"
      />
      <div className="min-w-0 flex-1">
        <p className="min-w-0 truncate text-sm font-semibold">
          {record.map_name}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-200">
          <StageBadge
            stage={record.stage}
            className="shrink-0 px-1.5 py-0 text-[0.625rem] [text-shadow:none]"
          />
          <span className="whitespace-nowrap">
            {record.mode} · {record.teleports === 0 ? "PRO" : "NUB"}
          </span>
          <span>
            {rank === null
              ? t("profile.pinned.rankUnavailable")
              : totalCount === null
                ? `#${formatNumber(rank)}`
                : `#${formatNumber(rank)} / ${formatCompactCount(totalCount)}`}
          </span>
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="flex items-center justify-end gap-2">
          <p className="text-xl font-semibold tracking-tight text-white tabular-nums">
            {formatRecordTime(record.time)}
          </p>
          <PointsBadge
            points={record.points}
            className="min-w-0 px-1.5 py-0 text-[0.625rem] [text-shadow:none]"
          />
        </div>
        <div className="mt-1">
          <span className="whitespace-nowrap text-[0.625rem] text-slate-200">
            {formatDateTime(record.created_on, {
              dateOnly: true,
              display: "absolute",
              fallback: "-",
            })}
          </span>
        </div>
      </div>
    </Link>
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
  onUnpinRecord: (mapId: number, stage: number, type: "NUB" | "PRO") => void
}) {
  const { t } = useTranslation()
  return (
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-[#eeece9] py-0 shadow-[0_1px_3px_rgb(0_0_0/0.06)] dark:bg-card/95 dark:shadow-sm">
      <CardContent className="space-y-4 p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
          {t("profile.pinned.title")}
        </p>

        {loading ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,22rem),1fr))] gap-2">
            {Array.from({ length: 6 }, (_, index) => (
              <Skeleton key={index} className="h-[76px] rounded-[14px]" />
            ))}
          </div>
        ) : pinnedRecords.length > 0 ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,22rem),1fr))] gap-2">
            {pinnedRecords.map(
              ({ mapId, record, rank, totalCount, stage, type }) => {
                const content = (
                  <PinnedRecordCard
                    record={record}
                    rank={rank}
                    totalCount={totalCount}
                  />
                )

                if (!canManagePinnedRecords) {
                  return <div key={record.uuid}>{content}</div>
                }

                return (
                  <ManagedPinnedRecordCard
                    key={record.uuid}
                    record={record}
                    rank={rank}
                    totalCount={totalCount}
                    disabled={mutating}
                    onUnpin={() => onUnpinRecord(mapId, stage, type)}
                  />
                )
              },
            )}
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
  disabled,
  onUnpin,
  ...recordProps
}: Pick<ProfilePinnedRecord, "record" | "rank" | "totalCount"> & {
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
        <PinnedRecordCard
          {...recordProps}
          aria-haspopup="menu"
          aria-disabled={disabled}
          onContextMenu={(event: MouseEvent<HTMLAnchorElement>) => {
            event.preventDefault()
            contextMenuRequestedRef.current = true
            setMenuOpen(true)
          }}
          onKeyDown={(event: KeyboardEvent<HTMLAnchorElement>) => {
            if (
              event.key === "ContextMenu" ||
              (event.shiftKey && event.key === "F10")
            ) {
              event.preventDefault()
              contextMenuRequestedRef.current = true
              setMenuOpen(true)
            }
          }}
        />
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
  identifier,
  activityError,
  activityLoading,
  activityStat,
  canManagePinnedRecords,
  pinnedRecords,
  pinnedRecordsError,
  pinnedRecordsLoading,
  pinnedRecordsMutating,
  onUnpinRecord,
}: {
  identifier: string
  activityError: boolean
  activityLoading: boolean
  activityStat: PlayerDailyActivityPublic | null
  pinnedRecords: ProfilePinnedRecord[]
  pinnedRecordsError: boolean
  pinnedRecordsLoading: boolean
  pinnedRecordsMutating: boolean
  onUnpinRecord: (mapId: number, stage: number, type: "NUB" | "PRO") => void
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

      <ProfileSetupCard
        identifier={identifier}
        isOwner={canManagePinnedRecords}
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
