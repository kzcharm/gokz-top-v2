import { useMemo, useState } from "react"

import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"

import {
  type ProfileActivityYear,
  profileHomePlaceholder,
} from "./profile-home-placeholder"
import {
  formatCompactPercent,
  formatNumber,
  profileBadgeToneClasses,
} from "./profile-utils"

const activityTones = [
  "bg-muted/70",
  "bg-primary/15",
  "bg-primary/30",
  "bg-primary/55",
  "bg-primary",
]

function MainSummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[20px] border border-border/70 bg-background/65 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
    </div>
  )
}

function CompletionCard({
  title,
  completed,
  total,
  tiers,
}: {
  title: string
  completed: number
  total: number
  tiers: Array<{
    label: string
    complete: number
    total: number
    color: string
  }>
}) {
  return (
    <Card className="gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              {title}
            </p>
            <p className="mt-3 text-3xl font-semibold tracking-tight">
              {formatCompactPercent(completed / total)}
            </p>
          </div>
          <p className="text-sm text-muted-foreground">
            {formatNumber(completed)} / {formatNumber(total)}
          </p>
        </div>
        <div className="space-y-1.5">
          {tiers.map((tier) => {
            const width = `${(tier.complete / tier.total) * 100}%`
            return (
              <div
                key={tier.label}
                className="grid grid-cols-[38px_minmax(0,1fr)_68px] items-center gap-3"
              >
                <span className="text-xs font-semibold text-muted-foreground">
                  {tier.label}
                </span>
                <div className="h-5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full"
                    style={{ width, backgroundColor: tier.color }}
                  />
                </div>
                <span className="text-right font-mono text-xs text-muted-foreground">
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

function PinnedRecordsCard() {
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
            {profileHomePlaceholder.pinnedRecords.length} of 6
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {profileHomePlaceholder.pinnedRecords.map((record) => (
            <div
              key={`${record.map}-${record.time}`}
              className="group rounded-[22px] border border-border/70 bg-background/75 p-4 transition-colors hover:border-primary/35"
            >
              <p className="truncate text-sm font-semibold">{record.map}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {record.mode} · {record.variant} · {record.rank}
              </p>
              <p className="mt-4 text-2xl font-semibold tracking-tight text-primary">
                {record.time}
              </p>
              <div className="mt-3 flex items-center gap-2">
                <span
                  className={cn(
                    "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium",
                    profileBadgeToneClasses[record.badgeTone],
                  )}
                >
                  {record.badge}
                </span>
                <span className="text-xs text-muted-foreground">
                  {record.achievedOn}
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function ProfileHomeContent() {
  const placeholder = profileHomePlaceholder

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <MainSummaryCard
          label="Total Points"
          value={formatNumber(placeholder.summary.points)}
        />
        <MainSummaryCard label="Rank" value={placeholder.summary.ratingTier} />
        <MainSummaryCard
          label="Global Standing"
          value={`#${formatNumber(placeholder.summary.globalRank)}`}
        />
      </div>

      <div className="grid gap-6 2xl:grid-cols-2">
        <CompletionCard
          title="Overall completion"
          completed={placeholder.completion.overall.completed}
          total={placeholder.completion.overall.total}
          tiers={placeholder.completion.overall.tiers}
        />
        <CompletionCard
          title="Pro completion"
          completed={placeholder.completion.pro.completed}
          total={placeholder.completion.pro.total}
          tiers={placeholder.completion.pro.tiers}
        />
      </div>

      <ActivityCard />
      <PinnedRecordsCard />
    </div>
  )
}
