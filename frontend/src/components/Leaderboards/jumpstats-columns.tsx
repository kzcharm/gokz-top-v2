import type { ColumnDef } from "@tanstack/react-table"
import type { TFunction } from "i18next"

import type {
  JumpstatLeaderboardEntryPublic,
  JumpstatPublic,
  JumpstatType,
} from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { ModeBadge } from "@/components/Records/ModeBadge"
import { formatNumber } from "@/i18n/locale"

export type JumpstatsLeaderboardTableRow = JumpstatLeaderboardEntryPublic
export type ProfileJumpstatsTableRow = JumpstatPublic

export const JUMPSTAT_TYPE_OPTIONS: JumpstatType[] = [
  "LJ",
  "BH",
  "MBH",
  "WJ",
  "LAJ",
  "LAH",
  "JB",
  "LBH",
  "LWJ",
]

function formatDecimal(value: number, digits: number) {
  return formatNumber(value, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function getJumpstatTypeLabel(value: JumpstatType, t: TFunction) {
  return t(`leaderboards.jumpstats.types.${value}`)
}

export function getJumpstatsLeaderboardColumns(
  t: TFunction,
  {
    blockEnabled,
  }: {
    blockEnabled: boolean
  },
): ColumnDef<JumpstatsLeaderboardTableRow>[] {
  const columns: ColumnDef<JumpstatsLeaderboardTableRow>[] = [
    {
      accessorKey: "rank",
      size: 56,
      header: () => <div className="flex w-full justify-center">#</div>,
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-semibold tabular-nums">
          {formatNumber(row.original.rank)}
        </div>
      ),
    },
    {
      accessorKey: "player",
      size: 288,
      header: () => t("labels.player"),
      enableSorting: false,
      cell: ({ row }) => <PlayerDisplay player={row.original.player} />,
    },
    {
      accessorKey: "mode",
      size: 88,
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
      size: 140,
      header: () => (
        <div className="flex w-full justify-center">
          {t("leaderboards.jumpstats.columns.distance")}
        </div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {formatDecimal(row.original.distance, 4)}
        </div>
      ),
    },
    {
      accessorKey: "strafes",
      size: 104,
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
      size: 104,
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
      size: 112,
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
      size: 112,
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
      size: 144,
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
      size: 184,
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

  if (blockEnabled) {
    columns.splice(4, 0, {
      accessorKey: "block",
      size: 96,
      header: () => (
        <div className="flex w-full justify-center">
          {t("leaderboards.jumpstats.columns.block")}
        </div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {row.original.block == null ? "-" : formatNumber(row.original.block)}
        </div>
      ),
    })
  }

  return columns
}

export function getProfileJumpstatsColumns(
  t: TFunction,
  {
    blockEnabled,
  }: {
    blockEnabled: boolean
  },
): ColumnDef<ProfileJumpstatsTableRow>[] {
  const columns: ColumnDef<ProfileJumpstatsTableRow>[] = [
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
      header: () => (
        <div className="flex w-full justify-center">
          {t("leaderboards.jumpstats.columns.distance")}
        </div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {formatDecimal(row.original.distance, 4)}
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

  if (blockEnabled) {
    columns.splice(2, 0, {
      accessorKey: "block",
      header: () => (
        <div className="flex w-full justify-center">
          {t("leaderboards.jumpstats.columns.block")}
        </div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center font-medium tabular-nums">
          {row.original.block == null ? "-" : formatNumber(row.original.block)}
        </div>
      ),
    })
  }

  return columns
}
