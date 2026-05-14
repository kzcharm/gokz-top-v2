import type { ColumnDef } from "@tanstack/react-table"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"

import type { RecordPublic } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { ModeBadge } from "@/components/Records/ModeBadge"
import { PointsBadge } from "@/components/Records/PointsBadge"
import { TeleportsBadge } from "@/components/Records/TeleportsBadge"
import { formatRecordTime } from "@/components/Records/utils"
import { cn, truncateText } from "@/lib/utils"

type MapTopTableRow = {
  rank: number
  record: RecordPublic
}

export function MapTopTable({
  records,
  emptyMessage,
  isLoading,
  pageIndex,
  pageSize,
  totalCount,
  onPageChange,
  onPageSizeChange,
  currentUserSteamid64,
}: {
  records: RecordPublic[]
  emptyMessage: string
  isLoading: boolean
  pageIndex: number
  pageSize: number
  totalCount: number
  onPageChange: (pageIndex: number) => void
  onPageSizeChange: (pageSize: number) => void
  currentUserSteamid64: string | null
}) {
  const { t } = useTranslation()

  const tableData = useMemo<MapTopTableRow[]>(
    () =>
      records.map((record, index) => ({
        rank: pageIndex * pageSize + index + 1,
        record,
      })),
    [pageIndex, pageSize, records],
  )

  const columns = useMemo<ColumnDef<MapTopTableRow>[]>(
    () => [
      {
        accessorKey: "rank",
        header: () => t("labels.rank"),
        cell: ({ row }) => (
          <span className="font-mono font-semibold text-foreground/90">
            #{row.original.rank}
          </span>
        ),
      },
      {
        id: "player",
        header: () => t("labels.player"),
        cell: ({ row }) => (
          <PlayerDisplay
            player={row.original.record.player}
            className="max-w-[15rem]"
            nameMaxLength={24}
          />
        ),
      },
      {
        id: "mode",
        header: () => t("labels.mode"),
        cell: ({ row }) => <ModeBadge mode={row.original.record.mode} />,
      },
      {
        id: "tps",
        header: () => t("labels.tps"),
        cell: ({ row }) => (
          <TeleportsBadge teleports={row.original.record.teleports} />
        ),
      },
      {
        id: "time",
        header: () => <div className="text-right">{t("labels.time")}</div>,
        cell: ({ row }) => (
          <div className="text-right font-mono font-medium">
            {formatRecordTime(row.original.record.time)}
          </div>
        ),
      },
      {
        id: "points",
        header: () => t("labels.points"),
        cell: ({ row }) => <PointsBadge points={row.original.record.points} />,
      },
      {
        id: "server",
        header: () => t("labels.server"),
        cell: ({ row }) => (
          <span
            className="block max-w-[14rem] truncate text-sm text-foreground/90"
            title={row.original.record.server_name}
          >
            {truncateText(row.original.record.server_name, 32)}
          </span>
        ),
      },
      {
        id: "datetime",
        header: () => t("labels.datetime"),
        cell: ({ row }) => (
          <FormattedDateTime
            className="text-sm text-muted-foreground"
            value={row.original.record.created_on}
            display="contextual-relative"
            fallback="-"
          />
        ),
      },
    ],
    [t],
  )

  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize))

  return (
    <div className="overflow-visible rounded-[28px] border border-border/70 bg-card shadow-sm">
      <div className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
        <DataTable
          columns={columns}
          data={tableData}
          isLoading={isLoading}
          emptyText={emptyMessage}
          stickyHeader
          stickyHeaderTopClassName="top-16"
          tableContainerClassName="md:overflow-visible"
          tableClassName="border-separate border-spacing-0"
          showFooter={false}
          getRowProps={(row) => ({
            "data-player-steamid64": row.record.player.steamid64,
            className:
              row.record.player.steamid64 === currentUserSteamid64
                ? cn(
                    "bg-primary/10 ring-1 ring-inset ring-primary/35",
                    "transition-[background-color,box-shadow,transform] duration-500",
                    "hover:bg-primary/15",
                  )
                : undefined,
          })}
          serverPagination={{
            pageIndex,
            pageSize,
            totalCount,
            onPageChange,
            onPageSizeChange: (nextPageSize) => {
              onPageSizeChange(nextPageSize)
              onPageChange(0)
            },
          }}
        />
        <TablePaginationFooter
          totalLabel={t("labels.records")}
          totalCount={totalCount}
          pageIndex={pageIndex}
          pageCount={pageCount}
          pageSize={pageSize}
          onPageIndexChange={onPageChange}
          onPageSizeChange={(nextPageSize) => {
            onPageSizeChange(nextPageSize)
            onPageChange(0)
          }}
        />
      </div>
    </div>
  )
}
