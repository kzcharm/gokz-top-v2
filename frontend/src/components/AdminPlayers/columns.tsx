import type { ColumnDef } from "@tanstack/react-table"
import { ArrowDown, ArrowUp } from "lucide-react"

import type { PlayerPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { Button } from "@/components/ui/button"

function SortableDateHeader({
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

export const columns: ColumnDef<PlayerPublic>[] = [
  {
    accessorKey: "name",
    header: "Player",
    cell: ({ row }) => <PlayerDisplay player={row.original} />,
  },
  {
    accessorKey: "created_at",
    header: ({ column }) => (
      <SortableDateHeader title="Created At" column={column} />
    ),
    cell: ({ row }) => (
      <FormattedDateTime
        className="text-muted-foreground"
        value={row.original.created_at}
        fallback="N/A"
      />
    ),
  },
  {
    accessorKey: "last_played_at",
    header: ({ column }) => (
      <SortableDateHeader title="Last Played At" column={column} />
    ),
    cell: ({ row }) => (
      <FormattedDateTime
        className="text-muted-foreground"
        value={row.original.last_played_at}
        fallback="N/A"
      />
    ),
  },
]
