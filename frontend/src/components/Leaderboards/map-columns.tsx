import type { ColumnDef } from "@tanstack/react-table"
import type { TFunction } from "i18next"
import { ArrowDown, ArrowUp, Star } from "lucide-react"

import type { MapLeaderboardEntryPublic } from "@/client"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Button } from "@/components/ui/button"
import { formatNumber, getLocale } from "@/i18n/locale"
import { cn } from "@/lib/utils"

export type MapLeaderboardSortField =
  | "name"
  | "tier"
  | "overall_avg"
  | "total_finishes"
  | "total_playtime"
  | "average_playtime_per_player"
  | "average_first_completion_time"
  | "median_first_completion_time"
  | "average_finishes_per_player"
  | "pro_nub_ratio"
  | "unique_pro_finishes"
  | "unique_nub_finishes"

export type MapLeaderboardTableRow = MapLeaderboardEntryPublic

function formatInteger(value: number) {
  return formatNumber(value)
}

function formatDecimal(
  value: number,
  minimumFractionDigits = 0,
  maximumFractionDigits = 2,
) {
  return new Intl.NumberFormat(getLocale(), {
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(value)
}

function formatPercentage(value: number, maximumFractionDigits = 1) {
  return `${new Intl.NumberFormat(getLocale(), {
    minimumFractionDigits: 0,
    maximumFractionDigits,
  }).format(value * 100)}%`
}

function formatHours(value: number) {
  return `${formatInteger(Math.round(value / 3600))} h`
}

function formatHoursMinutesSeconds(value: number) {
  const totalSeconds = Math.max(0, Math.round(value))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds
      .toString()
      .padStart(2, "0")}`
  }

  return `${minutes}:${seconds.toString().padStart(2, "0")}`
}

function SortableHeader({
  title,
  column,
  align = "left",
}: {
  title: string
  column: {
    getIsSorted: () => false | "asc" | "desc"
    toggleSorting: (desc?: boolean) => void
  }
  align?: "left" | "center" | "right"
}) {
  const sorting = column.getIsSorted()
  const justifyClassName =
    align === "right"
      ? "justify-end"
      : align === "center"
        ? "justify-center"
        : "justify-start"

  return (
    <div className={`flex w-full ${justifyClassName}`}>
      <Button
        type="button"
        variant="ghost"
        className="h-7 px-2 text-xs"
        onClick={() => column.toggleSorting(sorting !== "desc")}
      >
        {title}
        {sorting === "desc" ? <ArrowDown className="ml-2 size-4" /> : null}
        {sorting === "asc" ? <ArrowUp className="ml-2 size-4" /> : null}
      </Button>
    </div>
  )
}

function integerMetricColumn(
  accessorKey: "total_finishes" | "unique_pro_finishes" | "unique_nub_finishes",
  title: string,
): ColumnDef<MapLeaderboardTableRow> {
  return {
    accessorKey,
    header: ({ column }) => (
      <SortableHeader title={title} column={column} align="center" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-center font-medium tabular-nums">
        {formatInteger(row.original[accessorKey])}
      </div>
    ),
  }
}

function OverallRatingStars({
  t,
  overall,
  reviewsCount,
}: {
  t: TFunction
  overall: number | null
  reviewsCount: number
}) {
  const filledStars = overall === null ? 0 : Math.round(overall)
  const averageLabel = overall === null ? "0.0" : overall.toFixed(1)

  return (
    <div className="flex items-center gap-2">
      <div
        className="flex items-center gap-0.5"
        role="img"
        aria-label={
          reviewsCount === 0 || overall === null
            ? t("reviews.noReviewsAria")
            : t("reviews.reviewsAria", {
                rating: overall.toFixed(2),
                count: reviewsCount,
              })
        }
      >
        {Array.from({ length: 5 }, (_, index) => (
          <Star
            key={index}
            className={cn(
              "size-3.5",
              index < filledStars
                ? "fill-amber-400 text-amber-400"
                : "fill-transparent text-muted-foreground/35",
            )}
          />
        ))}
      </div>
      <span className="text-sm font-medium tabular-nums text-foreground">
        {averageLabel}
      </span>
      <span className="text-sm text-muted-foreground">({reviewsCount})</span>
    </div>
  )
}

function timeMetricColumn(
  accessorKey:
    | "average_playtime_per_player"
    | "average_first_completion_time"
    | "median_first_completion_time",
  title: string,
): ColumnDef<MapLeaderboardTableRow> {
  return {
    accessorKey,
    header: ({ column }) => (
      <SortableHeader title={title} column={column} align="center" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-center font-medium tabular-nums">
        {formatHoursMinutesSeconds(row.original[accessorKey])}
      </div>
    ),
  }
}

function decimalMetricColumn(
  accessorKey: "pro_nub_ratio",
  title: string,
  maximumFractionDigits: number,
): ColumnDef<MapLeaderboardTableRow> {
  return {
    accessorKey,
    header: ({ column }) => (
      <SortableHeader title={title} column={column} align="center" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-center font-medium tabular-nums">
        {formatPercentage(row.original[accessorKey], maximumFractionDigits)}
      </div>
    ),
  }
}

export function getMapLeaderboardColumns(
  t: TFunction,
): ColumnDef<MapLeaderboardTableRow>[] {
  return [
    {
      accessorKey: "name",
      header: ({ column }) => (
        <SortableHeader
          title={t("labels.map")}
          column={column}
          align="center"
        />
      ),
      cell: ({ row }) => (
        <div className="flex w-full justify-center">
          <MapDisplay mapName={row.original.map.name} />
        </div>
      ),
    },
    {
      accessorKey: "tier",
      header: ({ column }) => (
        <SortableHeader
          title={t("labels.tier")}
          column={column}
          align="center"
        />
      ),
      cell: ({ row }) => (
        <div className="flex w-full justify-center">
          <TierBadge tier={row.original.tier} />
        </div>
      ),
    },
    {
      accessorKey: "total_playtime",
      header: ({ column }) => (
        <SortableHeader
          title={t("leaderboards.mapColumns.playtime")}
          column={column}
          align="center"
        />
      ),
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {formatHours(row.original.total_playtime)}
        </div>
      ),
    },
    timeMetricColumn(
      "average_playtime_per_player",
      t("leaderboards.mapColumns.averagePlaytime"),
    ),
    integerMetricColumn("unique_nub_finishes", "NUB"),
    integerMetricColumn("unique_pro_finishes", "PRO"),
    decimalMetricColumn(
      "pro_nub_ratio",
      t("leaderboards.mapColumns.proRatio"),
      1,
    ),
    integerMetricColumn(
      "total_finishes",
      t("leaderboards.mapColumns.finishes"),
    ),
    {
      accessorKey: "average_finishes_per_player",
      header: ({ column }) => (
        <SortableHeader
          title={t("leaderboards.mapColumns.averageFinishes")}
          column={column}
          align="center"
        />
      ),
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {formatDecimal(row.original.average_finishes_per_player, 2, 2)}
        </div>
      ),
    },
    timeMetricColumn(
      "average_first_completion_time",
      t("leaderboards.mapColumns.firstAverage"),
    ),
    timeMetricColumn(
      "median_first_completion_time",
      t("leaderboards.mapColumns.firstMedian"),
    ),
    {
      accessorKey: "overall_avg",
      header: ({ column }) => (
        <SortableHeader title={t("labels.ratings")} column={column} />
      ),
      cell: ({ row }) => (
        <OverallRatingStars
          t={t}
          overall={row.original.review_summary?.overall_avg ?? null}
          reviewsCount={row.original.review_summary?.reviews_count ?? 0}
        />
      ),
    },
  ]
}
