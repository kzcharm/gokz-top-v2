import { PinOff } from "lucide-react"
import type { KeyboardEvent, MouseEvent, ReactNode } from "react"
import { useEffect, useMemo, useRef, useState } from "react"
import type { PlayerDailyActivityPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PointsBadge } from "@/components/Records/PointsBadge"
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
import { useHorizontalDragScroll } from "@/hooks/useHorizontalDragScroll"
import { cn } from "@/lib/utils"
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
const CONTRIBUTION_DAY_LABELS = [
  "Sun",
  "Mon",
  "Tue",
  "Wed",
  "Thu",
  "Fri",
  "Sat",
]
const CONTRIBUTION_MONTH_LABELS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const

type ActivityCell = {
  date: string
  count: number
  isEmpty: boolean
  level: number
}

type ActivityMonthLabel = {
  month: (typeof CONTRIBUTION_MONTH_LABELS)[number]
  weekIndex: number
}

function PaddedAverageNumber({ value }: { value: number }) {
  const formattedValue = formatNumber(value)
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
                      alt={`${trophy} trophy`}
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
              return (
                <div
                  key={tier.label}
                  className="grid grid-cols-[72px_minmax(0,1fr)_auto] items-center gap-2 sm:grid-cols-[80px_minmax(0,1fr)_58px] sm:gap-3"
                >
                  <span className="text-right text-[11px] font-semibold leading-4 text-muted-foreground sm:text-xs">
                    {tier.label} (avg{" "}
                    <PaddedAverageNumber value={tier.averagePoints} />)
                  </span>
                  <div className="h-5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full"
                      style={{ width, backgroundColor: tier.color }}
                    />
                  </div>
                  <span className="text-right font-mono text-[11px] tabular-nums text-muted-foreground sm:text-left sm:text-xs">
                    {tier.complete}/{tier.total}
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
  year,
}: {
  days: Array<{ date: string; count: number }>
  year: string
}) {
  const selectedYear = Number(year)
  const yearStart = new Date(Date.UTC(selectedYear, 0, 1))
  const yearEnd = new Date(Date.UTC(selectedYear, 11, 31))
  const countsByDate = new Map(
    days
      .filter((day) => day.date.startsWith(`${year}-`))
      .map((day) => [day.date, day.count]),
  )
  const weeks: ActivityCell[][] = []
  let currentWeek: ActivityCell[] = []
  const current = new Date(yearStart)
  const startDayOfWeek = current.getUTCDay()

  for (let dayIndex = 0; dayIndex < startDayOfWeek; dayIndex += 1) {
    currentWeek.push({
      date: `${year}-empty-0-${dayIndex}`,
      count: 0,
      isEmpty: true,
      level: 0,
    })
  }

  while (current <= yearEnd) {
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
        date: `${year}-empty-${weeks.length}-${currentWeek.length}`,
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
        month: CONTRIBUTION_MONTH_LABELS[monthIndex],
        weekIndex,
      })
      lastMonth = monthIndex
    }
  }

  return {
    monthLabels,
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
  const activityScrollRef = useHorizontalDragScroll<HTMLDivElement>()
  const allDays = activityStat?.days ?? []
  const availableYears = useMemo(() => {
    const years = Array.from(
      new Set(allDays.map((day) => day.date.slice(0, 4))),
    )
    years.sort((left, right) => right.localeCompare(left))
    return years
  }, [allDays])
  const fallbackYear = getCurrentUtcYear()
  const selectableYears =
    availableYears.length > 0 ? availableYears : [fallbackYear]
  const [activeYear, setActiveYear] = useState(
    selectableYears[0] ?? fallbackYear,
  )

  useEffect(() => {
    const nextYear = selectableYears[0] ?? fallbackYear
    setActiveYear((currentYear) =>
      selectableYears.includes(currentYear) ? currentYear : nextYear,
    )
  }, [fallbackYear, selectableYears])

  const { hasActivity, monthLabels, weeks } = useMemo(() => {
    return buildActivityCalendar({
      days: allDays,
      year: activeYear,
    })
  }, [activeYear, allDays])

  if (activityLoading) {
    return (
      <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
        <CardContent className="space-y-5 p-6">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                Activity
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
              Activity
            </p>
          </div>
          <div className="inline-flex rounded-full border border-border/70 bg-background/75 p-1">
            {selectableYears.map((year) => (
              <button
                key={year}
                type="button"
                onClick={() => setActiveYear(year)}
                data-testid={`profile-activity-year-${year}`}
                className={cn(
                  "rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                  activeYear === year
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )}
              >
                {year}
              </button>
            ))}
          </div>
        </div>

        {activityError ? (
          <p className="text-sm text-destructive">
            Unable to load daily activity right now.
          </p>
        ) : null}

        <div ref={activityScrollRef} className="overflow-x-auto">
          <div className="flex w-full justify-center">
            <div className="min-w-fit">
              <div
                className="relative ml-8 h-4"
                style={{ width: `${weeks.length * 13}px` }}
              >
                {monthLabels.map((label) => (
                  <span
                    key={`${activeYear}-${label.month}`}
                    className="absolute top-0 text-[11px] leading-4 text-muted-foreground"
                    style={{ left: `${label.weekIndex * 13}px` }}
                  >
                    {label.month}
                  </span>
                ))}
              </div>

              <div className="mt-2 flex gap-2">
                <div className="flex flex-col justify-around pt-px text-[11px] leading-[10px] text-muted-foreground">
                  {[1, 3, 5].map((dayIndex) => (
                    <span
                      key={CONTRIBUTION_DAY_LABELS[dayIndex]}
                      className="h-[23px]"
                    >
                      {CONTRIBUTION_DAY_LABELS[dayIndex]}
                    </span>
                  ))}
                </div>

                <div className="flex gap-[3px]">
                  {weeks.map((week, weekIndex) => (
                    <div
                      key={`${activeYear}-week-${weekIndex}`}
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
                          <span
                            key={`${weekIndex}-${dayIndex}-${day.date}`}
                            data-testid={`profile-activity-cell-${day.date}`}
                            data-activity-level={day.level}
                            title={`${day.count} ${day.count === 1 ? "record" : "records"} on ${day.date} UTC`}
                            className={cn(
                              "h-2.5 w-2.5 shrink-0 rounded-[2px] border border-[rgba(27,31,35,0.06)] transition-colors hover:border-muted-foreground/45 dark:border-[#1b1f23] dark:hover:border-muted-foreground/55",
                              activityToneClasses[day.level],
                            )}
                          />
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
            No record submissions found for {activeYear}.
          </p>
        ) : null}

        <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <span>Less</span>
          {activityToneClasses.map((tone, index) => (
            <span
              key={index}
              className={cn(
                "h-2.5 w-2.5 rounded-[2px] border border-[rgba(27,31,35,0.06)] dark:border-[#1b1f23]",
                tone,
              )}
            />
          ))}
          <span>More</span>
        </div>
      </CardContent>
    </Card>
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
  return (
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Pinned records
            </p>
          </div>
          <p className="text-sm text-muted-foreground">
            {pinnedRecords.length} of 6
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
                      ? "Rank unavailable"
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
            No pinned records found for this scope.
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
          Unpin this record
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
  pinnedRecords,
  pinnedRecordsError,
  pinnedRecordsLoading,
  pinnedRecordsMutating,
  onUnpinRecord,
}: {
  activityError: boolean
  activityLoading: boolean
  activityStat: PlayerDailyActivityPublic | null
  pinnedRecords: ProfilePinnedRecord[]
  pinnedRecordsError: boolean
  pinnedRecordsLoading: boolean
  pinnedRecordsMutating: boolean
  onUnpinRecord: (mapId: number, type: "NUB" | "PRO") => void
  canManagePinnedRecords: boolean
}) {
  return (
    <div className="min-w-0 space-y-6">
      <ActivityCard
        activityError={activityError}
        activityLoading={activityLoading}
        activityStat={activityStat}
      />
      {pinnedRecordsError ? (
        <Alert variant="destructive">
          <AlertTitle>Unable to load pinned record ranks</AlertTitle>
          <AlertDescription>Reload the page and try again.</AlertDescription>
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
          <AlertTitle>Unable to load completion progress</AlertTitle>
          <AlertDescription>
            The profile completion bars could not be loaded. Reload the page and
            try again.
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
            title="NUB completion"
            completed={completion.nub.completed}
            total={completion.nub.total}
            tiers={completion.nub.tiers}
            trophies={completionTrophies.nub}
          />
          <CompletionCard
            title="PRO completion"
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
