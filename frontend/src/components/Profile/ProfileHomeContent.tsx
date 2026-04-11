import { PinOff } from "lucide-react"
import type { KeyboardEvent, MouseEvent, ReactNode } from "react"
import { useEffect, useMemo, useRef, useState } from "react"

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
import { cn } from "@/lib/utils"

import {
  type ProfileActivityYear,
  profileHomePlaceholder,
} from "./profile-home-placeholder"
import {
  formatNumber,
  type ProfileCompletionData,
  type ProfilePinnedRecord,
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
const PROFILE_COMPLETION_TWO_COLUMN_MIN_WIDTH = 960

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

function CompletionCardsSkeleton({
  twoColumns,
}: {
  twoColumns: boolean
}) {
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
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
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
        <div
          onContextMenu={(event: MouseEvent<HTMLDivElement>) => {
            event.preventDefault()
            contextMenuRequestedRef.current = true
            setMenuOpen(true)
          }}
          onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
            if (
              event.key === "ContextMenu" ||
              (event.shiftKey && event.key === "F10")
            ) {
              event.preventDefault()
              contextMenuRequestedRef.current = true
              setMenuOpen(true)
            }
          }}
          tabIndex={0}
        >
          {children}
        </div>
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
  canManagePinnedRecords,
  pinnedRecords,
  pinnedRecordsError,
  pinnedRecordsLoading,
  pinnedRecordsMutating,
  onUnpinRecord,
}: {
  pinnedRecords: ProfilePinnedRecord[]
  pinnedRecordsError: boolean
  pinnedRecordsLoading: boolean
  pinnedRecordsMutating: boolean
  onUnpinRecord: (mapId: number, type: "NUB" | "PRO") => void
  canManagePinnedRecords: boolean
}) {
  return (
    <div className="min-w-0 space-y-6">
      <ActivityCard />
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
