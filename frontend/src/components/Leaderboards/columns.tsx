import type { ColumnDef } from "@tanstack/react-table"
import { ArrowDown, ArrowUp } from "lucide-react"

import type { PlayerLeaderboardEntryPublic } from "@/client"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { Button } from "@/components/ui/button"

function formatMetric(value: number) {
  return new Intl.NumberFormat("en-US").format(value)
}

function SortableHeader({
  title,
  column,
}: {
  title: string
  column: {
    getIsSorted: () => false | "asc" | "desc"
    toggleSorting: (desc?: boolean) => void
  }
}) {
  const sorting = column.getIsSorted()
  return (
    <Button
      type="button"
      variant="ghost"
      className="-ml-3 h-8 px-3"
      onClick={() => column.toggleSorting(sorting === "asc")}
    >
      {title}
      {sorting === "asc" ? (
        <ArrowUp className="ml-2 size-4" />
      ) : sorting === "desc" ? (
        <ArrowDown className="ml-2 size-4" />
      ) : null}
    </Button>
  )
}

function metricColumn(
  accessorKey:
    | "rating"
    | "rating_easy"
    | "rating_hard"
    | "points"
    | "wrs_nub"
    | "wrs_pro"
    | "records_900_plus"
    | "records_800_plus"
    | "unique_map_finishes",
  title: string,
): ColumnDef<PlayerLeaderboardEntryPublic> {
  return {
    accessorKey,
    header: ({ column }) => <SortableHeader title={title} column={column} />,
    cell: ({ row }) => (
      <span className="font-medium tabular-nums">
        {formatMetric(row.original[accessorKey])}
      </span>
    ),
  }
}

export const columns: ColumnDef<PlayerLeaderboardEntryPublic>[] = [
  {
    accessorKey: "rank",
    header: "#",
    cell: ({ row }) => (
      <span className="font-semibold tabular-nums">{row.original.rank}</span>
    ),
  },
  {
    accessorKey: "player",
    header: "Player",
    cell: ({ row }) => <PlayerDisplay player={row.original.player} />,
  },
  metricColumn("rating", "Rating"),
  metricColumn("rating_easy", "Rating Easy"),
  metricColumn("rating_hard", "Rating Hard"),
  metricColumn("points", "Points"),
  metricColumn("wrs_nub", "WRs NUB"),
  metricColumn("wrs_pro", "WRs PRO"),
  metricColumn("records_900_plus", "900+"),
  metricColumn("records_800_plus", "800+"),
  metricColumn("unique_map_finishes", "Unique Maps"),
]
