import type { ColumnDef } from "@tanstack/react-table"
import { ArrowDown, ArrowUp, Star } from "lucide-react"

import type { MapLeaderboardEntryPublic } from "@/client"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export type MapLeaderboardSortField =
  | "name"
  | "tier"
  | "overall_avg"
  | "comments_count"
  | "total_finishes"
  | "total_playtime"
  | "average_playtime_per_player"
  | "average_finishes_per_player"
  | "unique_pro_finishes"
  | "unique_nub_finishes"

export type MapLeaderboardTableRow = MapLeaderboardEntryPublic

function formatInteger(value: number) {
  return new Intl.NumberFormat("en-US").format(value)
}

function formatDecimal(value: number, maximumFractionDigits = 2) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits,
  }).format(value)
}

function formatHours(value: number) {
  return `${formatInteger(Math.round(value / 3600))} h`
}

function formatHoursMinutes(value: number) {
  const totalMinutes = Math.max(0, Math.round(value / 60))
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60

  return `${hours.toString().padStart(2, "0")}:${minutes
    .toString()
    .padStart(2, "0")}`
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
        className="h-8 px-3"
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
  accessorKey:
    | "total_finishes"
    | "unique_pro_finishes"
    | "unique_nub_finishes",
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
  overall,
  reviewsCount,
}: {
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
            ? "No reviews, 0 out of 5 stars"
            : `${overall.toFixed(2)} out of 5 stars from ${reviewsCount} reviews`
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

function ratingColumn(): ColumnDef<MapLeaderboardTableRow> {
  return {
    accessorKey: "overall_avg",
    header: ({ column }) => (
      <SortableHeader title="Rating" column={column} />
    ),
    cell: ({ row }) => (
      <OverallRatingStars
        overall={row.original.review_summary?.overall_avg ?? null}
        reviewsCount={row.original.review_summary?.reviews_count ?? 0}
      />
    ),
  }
}

function totalPlaytimeColumn(): ColumnDef<MapLeaderboardTableRow> {
  return {
    accessorKey: "total_playtime",
    header: ({ column }) => (
      <SortableHeader title="Playtime" column={column} align="center" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-center font-medium tabular-nums">
        {formatHours(row.original.total_playtime)}
      </div>
    ),
  }
}

function averagePlaytimeColumn(): ColumnDef<MapLeaderboardTableRow> {
  return {
    accessorKey: "average_playtime_per_player",
    header: ({ column }) => (
      <SortableHeader title="Avg Time" column={column} align="center" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-center font-medium tabular-nums">
        {formatHoursMinutes(row.original.average_playtime_per_player)}
      </div>
    ),
  }
}

export const mapLeaderboardColumns: ColumnDef<MapLeaderboardTableRow>[] = [
  {
    accessorKey: "name",
    header: ({ column }) => (
      <SortableHeader title="Map" column={column} align="center" />
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
      <SortableHeader title="Tier" column={column} align="center" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-center">
        <TierBadge tier={row.original.tier} />
      </div>
    ),
  },
  integerMetricColumn("total_finishes", "Finishes"),
  totalPlaytimeColumn(),
  averagePlaytimeColumn(),
  {
    accessorKey: "average_finishes_per_player",
    header: ({ column }) => (
      <SortableHeader title="Avg Finishes" column={column} align="center" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-center font-medium tabular-nums">
        {formatDecimal(row.original.average_finishes_per_player, 2)}
      </div>
    ),
  },
  integerMetricColumn("unique_pro_finishes", "PRO"),
  integerMetricColumn("unique_nub_finishes", "NUB"),
  ratingColumn(),
  {
    accessorKey: "comments_count",
    header: ({ column }) => (
      <SortableHeader title="Comments" column={column} align="center" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-center font-medium tabular-nums">
        {formatInteger(row.original.review_summary?.comments_count ?? 0)}
      </div>
    ),
  },
]
