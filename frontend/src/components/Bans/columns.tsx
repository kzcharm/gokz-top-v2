import type { ColumnDef } from "@tanstack/react-table"
import { Pencil } from "lucide-react"

import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { suppressRowInteractions } from "@/components/Common/interaction-suppression"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

import { formatBanTypeLabel, getBanStatus } from "./ban-status"

type BanPlayer = {
  display_name?: string | null
  steamid64: string
}

export interface BanRow {
  uuid: string
  id?: number | null
  ban_type: string
  created_at: string
  expires_at: string | null
  notes: string | null
  player: BanPlayer | null
  stats: string | null
  updated_by_player?: BanPlayer | null
  updated_by_steamid64?: string | null
}

function StatusBadge({
  createdAt,
  expiresAt,
}: {
  createdAt: string
  expiresAt: string | null
}) {
  const { formatDateTime } = useDateTimeFormat()
  const solidBadgeClassName = "border-transparent text-white dark:text-white"
  const status = getBanStatus({ createdAt, expiresAt })

  if (status === "permanent") {
    return (
      <Badge
        className={cn(
          solidBadgeClassName,
          "bg-destructive hover:bg-destructive/90 dark:bg-destructive/60",
        )}
      >
        Permanent
      </Badge>
    )
  }

  if (status === "unbanned") {
    return (
      <Badge
        className={cn(
          solidBadgeClassName,
          "bg-sky-600 hover:bg-sky-600/90 dark:bg-sky-700",
        )}
      >
        Unbanned
      </Badge>
    )
  }

  if (status === "expired") {
    return (
      <Badge
        className={cn(
          solidBadgeClassName,
          "bg-emerald-600 hover:bg-emerald-600/90 dark:bg-emerald-700",
        )}
      >
        Expired
      </Badge>
    )
  }

  return (
    <Tooltip delayDuration={300}>
      <TooltipTrigger asChild>
        <Badge
          className={cn(
            solidBadgeClassName,
            "bg-orange-500 hover:bg-orange-500/90 dark:bg-orange-600",
          )}
        >
          {formatDateTime(expiresAt, {
            display: "absolute",
            dateOnly: true,
          })}
        </Badge>
      </TooltipTrigger>
      <TooltipContent
        hideArrow
        sideOffset={4}
        className="rounded-sm border border-border bg-background px-2 py-1 font-normal text-foreground shadow-md"
      >
        {formatDateTime(expiresAt, { display: "relative" })}
      </TooltipContent>
    </Tooltip>
  )
}

function toPlayerDisplay(player: BanPlayer | null | undefined) {
  if (!player) {
    return null
  }

  return {
    steamid64: player.steamid64,
    displayName: player.display_name ?? player.steamid64,
  }
}

export function getBanColumns({
  showUpdaterColumn,
  showEditActions,
  onEditBan,
}: {
  showUpdaterColumn: boolean
  showEditActions: boolean
  onEditBan: (ban: BanRow) => void
}): ColumnDef<BanRow>[] {
  const columns: ColumnDef<BanRow>[] = [
    {
      accessorKey: "player",
      header: "Player",
      cell: ({ row }) => (
        <PlayerDisplay
          player={toPlayerDisplay(row.original.player)}
          fallbackSteamid64={row.original.player?.steamid64}
          nameMaxLength={28}
        />
      ),
    },
    {
      accessorKey: "ban_type",
      header: "Ban Type",
      cell: ({ row }) => (
        <Badge variant="outline">
          {formatBanTypeLabel(row.original.ban_type)}
        </Badge>
      ),
    },
    {
      accessorKey: "expires_at",
      header: "Expires",
      cell: ({ row }) => (
        <StatusBadge
          createdAt={row.original.created_at}
          expiresAt={row.original.expires_at}
        />
      ),
    },
    {
      accessorKey: "notes",
      header: "Notes",
      cell: ({ row }) => (
        <div
          className="max-w-[280px] truncate text-sm text-muted-foreground"
          title={row.original.notes ?? ""}
        >
          {row.original.notes?.trim() || "No notes"}
        </div>
      ),
    },
    {
      accessorKey: "created_at",
      header: "Issued",
      cell: ({ row }) => (
        <FormattedDateTime
          value={row.original.created_at}
          display="contextual-relative"
        />
      ),
    },
  ]

  if (showUpdaterColumn) {
    columns.push({
      id: "updated_by_player",
      header: "Updated By",
      cell: ({ row }) =>
        row.original.updated_by_player ? (
          <PlayerDisplay
            player={toPlayerDisplay(row.original.updated_by_player)}
            fallbackSteamid64={row.original.updated_by_steamid64 ?? undefined}
            nameMaxLength={24}
          />
        ) : row.original.updated_by_steamid64 ? (
          <span className="text-sm text-muted-foreground">
            {row.original.updated_by_steamid64}
          </span>
        ) : (
          <span className="text-sm text-muted-foreground">-</span>
        ),
    })
  }

  if (showEditActions) {
    columns.push({
      id: "actions",
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => (
        <div className="flex justify-end">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={(event) => {
              suppressRowInteractions()
              event.preventDefault()
              event.stopPropagation()
              onEditBan(row.original)
            }}
            aria-label="Edit ban"
            title="Edit ban"
          >
            <Pencil className="size-4" />
          </Button>
        </div>
      ),
    })
  }

  return columns
}
