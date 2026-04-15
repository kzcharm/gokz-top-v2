import { Link } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { ArrowDown, ArrowUp } from "lucide-react"

import type { MapLeaderboardEntryPublic } from "@/client"
import { formatRecordTime } from "@/components/Records/utils"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Button } from "@/components/ui/button"

export type MapLeaderboardSortField =
  | "name"
  | "tier"
  | "overall_avg"
  | "gameplay_avg"
  | "visuals_avg"
  | "comments_count"
  | "unique_player_finishes"
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

function formatNullableRating(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "-"
  }
  return formatDecimal(value, 2)
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
    | "unique_player_finishes"
    | "total_finishes"
    | "unique_pro_finishes"
    | "unique_nub_finishes",
  title: string,
): ColumnDef<MapLeaderboardTableRow> {
  return {
    accessorKey,
    header: ({ column }) => (
      <SortableHeader title={title} column={column} align="right" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-end font-medium tabular-nums">
        {formatInteger(row.original[accessorKey])}
      </div>
    ),
  }
}

function ratingColumn(
  accessorKey: "overall_avg" | "gameplay_avg" | "visuals_avg",
  title: string,
): ColumnDef<MapLeaderboardTableRow> {
  return {
    accessorKey,
    header: ({ column }) => (
      <SortableHeader title={title} column={column} align="right" />
    ),
    cell: ({ row }) => {
      const value =
        accessorKey === "overall_avg"
          ? row.original.review_summary?.overall_avg
          : accessorKey === "gameplay_avg"
            ? row.original.review_summary?.gameplay_avg
            : row.original.review_summary?.visuals_avg

      return (
        <div className="flex w-full justify-end font-medium tabular-nums">
          {formatNullableRating(value)}
        </div>
      )
    },
  }
}

function playtimeColumn(
  accessorKey: "total_playtime" | "average_playtime_per_player",
  title: string,
): ColumnDef<MapLeaderboardTableRow> {
  return {
    accessorKey,
    header: ({ column }) => (
      <SortableHeader title={title} column={column} align="right" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-end font-medium tabular-nums">
        {formatRecordTime(row.original[accessorKey])}
      </div>
    ),
  }
}

export const mapLeaderboardColumns: ColumnDef<MapLeaderboardTableRow>[] = [
  {
    accessorKey: "name",
    header: ({ column }) => <SortableHeader title="Map" column={column} />,
    cell: ({ row }) => (
      <Link
        to="/maps/$mapName"
        params={{ mapName: row.original.map.name }}
        className="font-medium text-foreground transition-colors hover:text-primary hover:underline"
      >
        {row.original.map.name}
      </Link>
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
  integerMetricColumn("unique_player_finishes", "Unique"),
  integerMetricColumn("total_finishes", "Finishes"),
  playtimeColumn("total_playtime", "Playtime"),
  playtimeColumn("average_playtime_per_player", "Avg Time"),
  {
    accessorKey: "average_finishes_per_player",
    header: ({ column }) => (
      <SortableHeader title="Avg Finishes" column={column} align="right" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-end font-medium tabular-nums">
        {formatDecimal(row.original.average_finishes_per_player, 2)}
      </div>
    ),
  },
  integerMetricColumn("unique_pro_finishes", "PRO"),
  integerMetricColumn("unique_nub_finishes", "NUB"),
  ratingColumn("overall_avg", "Overall"),
  ratingColumn("gameplay_avg", "Gameplay"),
  ratingColumn("visuals_avg", "Visuals"),
  {
    accessorKey: "comments_count",
    header: ({ column }) => (
      <SortableHeader title="Comments" column={column} align="right" />
    ),
    cell: ({ row }) => (
      <div className="flex w-full justify-end font-medium tabular-nums">
        {formatInteger(row.original.review_summary?.comments_count ?? 0)}
      </div>
    ),
  },
]
