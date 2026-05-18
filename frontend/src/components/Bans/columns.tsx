import type { ColumnDef } from "@tanstack/react-table"

import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import { Badge } from "@/components/ui/badge"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

type BanPlayer = {
  display_name?: string | null
  steamid64: string
}

export interface BanRow {
  uuid: string
  id: number | null
  ban_type: string
  created_on: string
  expires_on: string | null
  notes: string | null
  player: BanPlayer | null
  stats: string | null
}

function formatBanTypeLabel(banType: string) {
  return banType
    .split("_")
    .map((segment) =>
      segment.length > 0
        ? `${segment[0].toUpperCase()}${segment.slice(1)}`
        : "",
    )
    .join(" ")
}

function ExpiryBadge({ expiresOn }: { expiresOn: string | null }) {
  const { formatDateTime } = useDateTimeFormat()
  const solidBadgeClassName = "border-transparent text-white dark:text-white"

  if (!expiresOn) {
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

  const expiresAt = new Date(expiresOn)
  const isExpired =
    !Number.isNaN(expiresAt.getTime()) && expiresAt.getTime() < Date.now()

  if (isExpired) {
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
          {formatDateTime(expiresOn, {
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
        {formatDateTime(expiresOn, { display: "relative" })}
      </TooltipContent>
    </Tooltip>
  )
}

export const banColumns: ColumnDef<BanRow>[] = [
  {
    accessorKey: "player",
    header: "Player",
    cell: ({ row }) => (
      <PlayerDisplay
        player={
          row.original.player
            ? {
                steamid64: row.original.player.steamid64,
                displayName:
                  row.original.player.display_name ??
                  row.original.player.steamid64,
              }
            : null
        }
        fallbackSteamid64={row.original.player?.steamid64}
        nameMaxLength={28}
      />
    ),
  },
  {
    accessorKey: "id",
    header: "Source",
    cell: ({ row }) =>
      row.original.id === null ? (
        <Badge variant="destructive">Admin-created</Badge>
      ) : (
        <Badge variant="outline">GlobalAPI</Badge>
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
    accessorKey: "expires_on",
    header: "Expires",
    cell: ({ row }) => <ExpiryBadge expiresOn={row.original.expires_on} />,
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
    accessorKey: "created_on",
    header: "Issued",
    cell: ({ row }) => (
      <FormattedDateTime
        value={row.original.created_on}
        display="contextual-relative"
      />
    ),
  },
]
