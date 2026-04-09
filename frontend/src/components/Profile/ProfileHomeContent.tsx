import { useMemo, useState } from "react"

import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PointsBadge } from "@/components/Records/PointsBadge"
import { formatCompactCount } from "@/components/Records/TeleportsBadge"
import { formatRecordTime } from "@/components/Records/utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

import {
  type ProfileActivityYear,
  profileHomePlaceholder,
} from "./profile-home-placeholder"
import {
  formatNumber,
  type ProfileCompletionData,
  type ProfilePinnedRecord,
  type ProfileSummaryData,
  type ProfileTrophyCounts,
} from "./profile-utils"

const activityTones = [
  "bg-muted/70",
  "bg-primary/15",
  "bg-primary/30",
  "bg-primary/55",
  "bg-primary",
]

const TROPHY_ASSETS = {
  gold: "https://kzgo.eu/trophy4.png",
  silver: "https://kzgo.eu/trophy_silver2.png",
  bronze: "https://kzgo.eu/trophy_bronze.png",
} as const

function PaddedAverageNumber({ value }: { value: number }) {
  const formattedValue = formatNumber(value)
  const paddedValue = formattedValue.padStart(3, "0")

  return <span className="font-mono tabular-nums">{paddedValue}</span>
}

function MainSummaryCard({
  label,
  loading,
  value,
}: {
  label: string
  loading?: boolean
  value: string
}) {
  return (
    <div className="rounded-[20px] border border-border bg-card p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </p>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-28" />
      ) : (
        <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
      )}
    </div>
  )
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
    <Card className="gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
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
                className="grid grid-cols-[80px_minmax(0,1fr)_58px] items-center gap-3"
              >
                <span className="text-right text-xs font-semibold text-muted-foreground">
                  {tier.label} (avg{" "}
                  <PaddedAverageNumber value={tier.averagePoints} />)
                </span>
                <div className="h-5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full"
                    style={{ width, backgroundColor: tier.color }}
                  />
                </div>
                <span className="text-left font-mono text-xs tabular-nums text-muted-foreground">
                  {tier.complete}/{tier.total}
                </span>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

function CompletionCardsSkeleton() {
  return (
    <div className="grid gap-6 2xl:grid-cols-2">
      {Array.from({ length: 2 }, (_, index) => (
        <Card
          key={index}
          className="gap-0 rounded-[26px] border-border/70 bg-card/95 py-0"
        >
          <CardContent className="space-y-5 p-6">
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
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function ActivityCard() {
  const [activeYear, setActiveYear] = useState<ProfileActivityYear>("2026")
  const levels = profileHomePlaceholder.activity[activeYear]

  const weeks = useMemo(() => {
    return Array.from({ length: 53 }, (_, weekIndex) =>
      Array.from(
        { length: 7 },
        (_, dayIndex) => levels[weekIndex * 7 + dayIndex],
      ),
    )
  }, [levels])

  return (
    <Card className="gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Activity
            </p>
          </div>
          <div className="inline-flex rounded-full border border-border/70 bg-background/75 p-1">
            {(["2025", "2026"] as const).map((year) => (
              <button
                key={year}
                type="button"
                onClick={() => setActiveYear(year)}
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

        <div className="overflow-x-auto">
          <div className="flex w-full justify-center">
            <div className="min-w-[720px] space-y-1.5">
              {Array.from({ length: 7 }, (_, rowIndex) => (
                <div key={rowIndex} className="flex gap-1.5">
                  {weeks.map((week, weekIndex) => (
                    <span
                      key={`${weekIndex}-${rowIndex}`}
                      className={cn(
                        "h-3 w-3 shrink-0 rounded-[4px] border border-black/0",
                        activityTones[week[rowIndex]],
                      )}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <span>Less</span>
          {activityTones.map((tone, index) => (
            <span key={index} className={cn("h-3 w-3 rounded-[4px]", tone)} />
          ))}
          <span>More</span>
        </div>
      </CardContent>
    </Card>
  )
}

function PinnedRecordsCard({
  pinnedRecords,
  loading,
}: {
  pinnedRecords: ProfilePinnedRecord[]
  loading: boolean
}) {
  return (
    <Card className="gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
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
            {pinnedRecords.map(({ record, rank, totalCount }) => (
              <div
                key={record.uuid}
                className="group rounded-[22px] border border-border/70 bg-background/75 p-4 transition-colors hover:border-primary/35"
              >
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
            ))}
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

export function ProfileHomeContent({
  completion,
  completionLoading,
  completionError,
  completionTrophies,
  pinnedRecords,
  pinnedRecordsError,
  pinnedRecordsLoading,
  summary,
  summaryLoading,
}: {
  completion: ProfileCompletionData
  completionLoading: boolean
  completionError: boolean
  completionTrophies: {
    nub: ProfileTrophyCounts
    pro: ProfileTrophyCounts
  }
  pinnedRecords: ProfilePinnedRecord[]
  pinnedRecordsError: boolean
  pinnedRecordsLoading: boolean
  summary: ProfileSummaryData
  summaryLoading: boolean
}) {
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <MainSummaryCard
          label="Total Points"
          loading={summaryLoading}
          value={formatNumber(summary.totalPoints)}
        />
        <MainSummaryCard
          label="Rank"
          loading={summaryLoading}
          value={summary.rankLabel}
        />
        <MainSummaryCard
          label="Global Standing"
          loading={summaryLoading}
          value={
            summary.globalStanding === null
              ? "Unranked"
              : `#${formatNumber(summary.globalStanding)}`
          }
        />
      </div>

      {completionError ? (
        <Alert variant="destructive">
          <AlertTitle>Unable to load completion progress</AlertTitle>
          <AlertDescription>
            The profile completion bars could not be loaded. Reload the page and
            try again.
          </AlertDescription>
        </Alert>
      ) : completionLoading ? (
        <CompletionCardsSkeleton />
      ) : (
        <div className="grid gap-6 2xl:grid-cols-2">
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

      <ActivityCard />
      {pinnedRecordsError ? (
        <Alert variant="destructive">
          <AlertTitle>Unable to load pinned record ranks</AlertTitle>
          <AlertDescription>Reload the page and try again.</AlertDescription>
        </Alert>
      ) : null}
      <PinnedRecordsCard
        pinnedRecords={pinnedRecords}
        loading={pinnedRecordsLoading}
      />
    </div>
  )
}
