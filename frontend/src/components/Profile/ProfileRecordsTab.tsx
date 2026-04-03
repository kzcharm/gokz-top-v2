import { useQuery } from "@tanstack/react-query"
import { startTransition, useEffect, useMemo, useRef, useState } from "react"

import { type RecordPublic, RecordsService } from "@/client"
import {
  type PbRecordsColumn,
  type PbRecordsSortState,
  PbRecordsTable,
} from "@/components/Records/PbRecordsTable"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"

const PROFILE_RECORDS_LIMIT = 10_000
const PROFILE_RECORDS_PAGE_SIZE = 50

function compareStrings(left: string, right: string) {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  })
}

function getRecordSortValue(column: PbRecordsColumn, record: RecordPublic) {
  switch (column) {
    case "player":
      return record.player_name
    case "map":
      return record.map_name
    case "mode":
      return record.mode
    case "tier":
      return record.map_tier
    case "tps":
      return record.teleports
    case "time":
      return record.time
    case "points":
      return record.points
    case "server":
      return record.server_name
    case "datetime":
      return Date.parse(record.created_on)
  }
}

function sortRecords(records: RecordPublic[], sort: PbRecordsSortState) {
  return [...records].sort((left, right) => {
    const leftValue = getRecordSortValue(sort.column, left)
    const rightValue = getRecordSortValue(sort.column, right)

    let comparison = 0
    if (typeof leftValue === "string" && typeof rightValue === "string") {
      comparison = compareStrings(leftValue, rightValue)
    } else {
      comparison = Number(leftValue) - Number(rightValue)
    }

    if (comparison === 0) {
      comparison = compareStrings(left.uuid, right.uuid)
    }

    return sort.direction === "asc" ? comparison : -comparison
  })
}

function ProfileRecordsTableSkeleton() {
  return (
    <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm">
      <div className="space-y-3 p-6">
        <Skeleton className="h-6 w-56" />
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-12 w-full" />
        ))}
      </div>
    </div>
  )
}

export function ProfileRecordsTab({ steamid64 }: { steamid64: string }) {
  const { scope } = useScope()
  const [isProOnly, setIsProOnly] = useState(false)
  const [sort, setSort] = useState<PbRecordsSortState>({
    column: "datetime",
    direction: "desc",
  })
  const [visibleCount, setVisibleCount] = useState(PROFILE_RECORDS_PAGE_SIZE)
  const loadMoreRef = useRef<HTMLDivElement | null>(null)

  const recordsQuery = useQuery({
    queryKey: ["profile-records", steamid64, scope, isProOnly],
    queryFn: () =>
      RecordsService.readPbRecords({
        steamid64,
        scope,
        stage: 0,
        isProOnly,
        limit: PROFILE_RECORDS_LIMIT,
      }),
    retry: 1,
  })

  const sortedRecords = useMemo(() => {
    return sortRecords(recordsQuery.data ?? [], sort)
  }, [recordsQuery.data, sort])

  const visibleRecords = useMemo(() => {
    return sortedRecords.slice(0, visibleCount)
  }, [sortedRecords, visibleCount])

  useEffect(() => {
    setVisibleCount(PROFILE_RECORDS_PAGE_SIZE)
  }, [recordsQuery.data, sort, scope, isProOnly, steamid64])

  useEffect(() => {
    const target = loadMoreRef.current
    if (!target || visibleCount >= sortedRecords.length) {
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (!entry?.isIntersecting) {
          return
        }

        startTransition(() => {
          setVisibleCount((current) =>
            Math.min(current + PROFILE_RECORDS_PAGE_SIZE, sortedRecords.length),
          )
        })
      },
      {
        rootMargin: "320px 0px",
      },
    )

    observer.observe(target)
    return () => observer.disconnect()
  }, [sortedRecords.length, visibleCount])

  const handleSortChange = (column: PbRecordsColumn) => {
    setSort((current) => {
      if (current.column === column) {
        return {
          column,
          direction: current.direction === "desc" ? "asc" : "desc",
        }
      }

      return {
        column,
        direction: "desc",
      }
    })
  }

  return (
    <div className="space-y-4">
      <Card className="gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
          <Label
            htmlFor="profile-records-pro-only"
            className="flex items-center gap-3 rounded-full border border-border/70 bg-background/70 px-3 py-2"
          >
            <Switch
              id="profile-records-pro-only"
              checked={isProOnly}
              onCheckedChange={setIsProOnly}
            />
            <span>Pro only</span>
          </Label>
        </CardContent>
      </Card>

      {recordsQuery.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load profile records. Reload the page and try again.
          </AlertDescription>
        </Alert>
      ) : null}

      {recordsQuery.isLoading ? (
        <ProfileRecordsTableSkeleton />
      ) : (
        <div className="space-y-4">
          <PbRecordsTable
            records={visibleRecords}
            columns={[
              "map",
              "mode",
              "tier",
              "tps",
              "time",
              "points",
              "server",
              "datetime",
            ]}
            emptyMessage={
              isProOnly
                ? "No stage 0 pro records found for this player in the selected scope."
                : "No stage 0 records found for this player in the selected scope."
            }
            dateTimeDisplay="contextual-relative"
            sort={sort}
            onSortChange={handleSortChange}
          />
          {visibleCount < sortedRecords.length ? (
            <div
              ref={loadMoreRef}
              className="flex h-14 items-center justify-center text-sm text-muted-foreground"
            >
              Loading more records...
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
