import type { ColumnDef } from "@tanstack/react-table"
import { ArrowDown, ArrowUp } from "lucide-react"

import type { UserPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { UserActionsMenu } from "./UserActionsMenu"

export type UserTableData = UserPublic & {
  isCurrentUser: boolean
}

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

export const columns: ColumnDef<UserTableData>[] = [
  {
    accessorKey: "player.name",
    header: "Player",
    cell: ({ row }) => (
      <div className="flex items-center gap-2">
        <PlayerDisplay
          player={row.original.player}
          fallbackSteamid64={row.original.steamid64}
        />
        {row.original.isCurrentUser && (
          <Badge variant="outline" className="text-xs">
            You
          </Badge>
        )}
      </div>
    ),
  },
  {
    accessorKey: "is_superuser",
    header: "Role",
    cell: ({ row }) => (
      <Badge variant={row.original.is_superuser ? "default" : "secondary"}>
        {row.original.is_superuser ? "Superuser" : "User"}
      </Badge>
    ),
  },
  {
    accessorKey: "created_at",
    header: ({ column }) => (
      <SortableDateHeader title="Created" column={column} />
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
    accessorKey: "last_visited_at",
    header: ({ column }) => (
      <SortableDateHeader title="Last Visited" column={column} />
    ),
    cell: ({ row }) => (
      <FormattedDateTime
        className="text-muted-foreground"
        value={row.original.last_visited_at}
        fallback="N/A"
      />
    ),
  },
  {
    id: "actions",
    header: () => <span className="sr-only">Actions</span>,
    cell: ({ row }) => (
      <div className="flex justify-end">
        <UserActionsMenu user={row.original} />
      </div>
    ),
  },
]
