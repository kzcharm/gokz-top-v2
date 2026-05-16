import type { ColumnDef } from "@tanstack/react-table"
import type { TFunction } from "i18next"
import { ArrowDown } from "lucide-react"

import type { JumpstatLeaderboardEntryPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { ModeBadge } from "@/components/Records/ModeBadge"
import { Button } from "@/components/ui/button"
import { formatNumber } from "@/i18n/locale"

export type JumpstatsLeaderboardTableRow = JumpstatLeaderboardEntryPublic

function formatDecimal(value: number, digits: number) {
  return formatNumber(value, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
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
  return (
    <div
      className={
        align === "right"
          ? "flex w-full justify-end"
          : "flex w-full justify-center"
      }
    >
      <Button
        type="button"
        variant="ghost"
        className="h-8 px-3"
        onClick={() => column.toggleSorting(true)}
      >
        {title}
        {sorting ? <ArrowDown className="ml-2 size-4" /> : null}
      </Button>
    </div>
  )
}

export function getJumpstatsLeaderboardColumns(
  t: TFunction,
): ColumnDef<JumpstatsLeaderboardTableRow>[] {
  return [
    {
      accessorKey: "rank",
      header: () => <div className="flex w-full justify-center">#</div>,
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-semibold tabular-nums">
          {formatNumber(row.original.rank)}
        </div>
      ),
    },
    {
      accessorKey: "player",
      header: () => t("labels.player"),
      enableSorting: false,
      cell: ({ row }) => <PlayerDisplay player={row.original.player} />,
    },
    {
      accessorKey: "mode",
      header: () => (
        <div className="flex w-full justify-center">{t("labels.mode")}</div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center">
          <ModeBadge mode={row.original.mode} />
        </div>
      ),
    },
    {
      accessorKey: "distance",
      header: ({ column }) => (
        <SortableHeader
          title={t("leaderboards.jumpstats.columns.distance")}
          column={column}
        />
      ),
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {formatDecimal(row.original.distance, 4)}
        </div>
      ),
    },
    {
      accessorKey: "block",
      header: ({ column }) => (
        <SortableHeader
          title={t("leaderboards.jumpstats.columns.block")}
          column={column}
        />
      ),
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {row.original.block == null ? "-" : formatNumber(row.original.block)}
        </div>
      ),
    },
    {
      accessorKey: "strafes",
      header: () => (
        <div className="flex w-full justify-center">
          {t("leaderboards.jumpstats.columns.strafes")}
        </div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {formatNumber(row.original.strafes)}
        </div>
      ),
    },
    {
      accessorKey: "sync_percent",
      header: () => (
        <div className="flex w-full justify-center">
          {t("leaderboards.jumpstats.columns.sync")}
        </div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {formatNumber(row.original.sync_percent)}%
        </div>
      ),
    },
    {
      accessorKey: "pre_speed",
      header: () => (
        <div className="flex w-full justify-center">
          {t("leaderboards.jumpstats.columns.pre")}
        </div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {formatDecimal(row.original.pre_speed, 2)}
        </div>
      ),
    },
    {
      accessorKey: "max_speed",
      header: () => (
        <div className="flex w-full justify-center">
          {t("leaderboards.jumpstats.columns.max")}
        </div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {formatDecimal(row.original.max_speed, 2)}
        </div>
      ),
    },
    {
      id: "server_group",
      header: () => (
        <div className="flex w-full justify-center">{t("labels.server")}</div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center text-center font-medium">
          {row.original.server_group.name}
        </div>
      ),
    },
    {
      accessorKey: "jumped_at",
      header: () => (
        <div className="flex w-full justify-center">
          {t("leaderboards.jumpstats.columns.jumpedAt")}
        </div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center">
          <FormattedDateTime
            value={row.original.jumped_at}
            display="absolute"
          />
        </div>
      ),
    },
  ]
}
