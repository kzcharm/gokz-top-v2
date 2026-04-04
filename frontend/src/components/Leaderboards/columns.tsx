import type { ColumnDef } from "@tanstack/react-table"
import { ArrowDown } from "lucide-react"

import type { PlayerLeaderboardEntryPublic } from "@/client"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { Button } from "@/components/ui/button"

function formatMetric(value: number) {
  return new Intl.NumberFormat("en-US").format(value)
}

function SortableHeader({
  title,
  column,
  align = "center",
}: {
  title: string
  column: {
    getIsSorted: () => false | "asc" | "desc"
    toggleSorting: (desc?: boolean) => void
  }
  align?: "center" | "right"
}) {
  const sorting = column.getIsSorted()
  const containerClassName =
    align === "right" ? "flex w-full justify-end" : "flex w-full justify-center"
  const buttonClassName =
    align === "right" ? "h-8 px-3" : "h-8 px-3"

  return (
    <div className={containerClassName}>
      <Button
        type="button"
        variant="ghost"
        className={buttonClassName}
        onClick={() => column.toggleSorting(true)}
      >
        {title}
        {sorting ? <ArrowDown className="ml-2 size-4" /> : null}
      </Button>
    </div>
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
  align: "center" | "right" = "center",
): ColumnDef<PlayerLeaderboardEntryPublic> {
  return {
    accessorKey,
    header: ({ column }) => (
      <SortableHeader title={title} column={column} align={align} />
    ),
    cell: ({ row }) => (
      <div
        className={
          align === "right"
            ? "flex w-full justify-end"
            : "flex w-full justify-center"
        }
      >
        <span className="font-medium tabular-nums">
          {formatMetric(row.original[accessorKey])}
        </span>
      </div>
    ),
  }
}

export const columns: ColumnDef<PlayerLeaderboardEntryPublic>[] = [
  {
    accessorKey: "rank",
    header: () => <div className="flex w-full justify-center">#</div>,
    cell: ({ row }) => (
      <div className="flex w-full justify-center">
        <span className="font-semibold tabular-nums">{row.original.rank}</span>
      </div>
    ),
  },
  {
    accessorKey: "player",
    header: "Player",
    cell: ({ row }) => <PlayerDisplay player={row.original.player} />,
  },
  metricColumn("rating", "Rating"),
  metricColumn("rating_easy", "Rating.E"),
  metricColumn("rating_hard", "Rating.H"),
  metricColumn("points", "Points", "right"),
  metricColumn("wrs_nub", "NUB WRs"),
  metricColumn("wrs_pro", "PRO WRs"),
  metricColumn("records_900_plus", "900+"),
  metricColumn("records_800_plus", "800+"),
  metricColumn("unique_map_finishes", "Maps"),
]
