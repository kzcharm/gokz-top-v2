import type { ColumnDef } from "@tanstack/react-table"
import { Flag, InfoIcon } from "lucide-react"
import type { ReactNode } from "react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import type { RecordPublic } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import {
  RowContextMenuItem,
  RowContextMenuSeparator,
} from "@/components/Common/RowContextMenu"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { ModeBadge } from "@/components/Records/ModeBadge"
import { PointsBadge } from "@/components/Records/PointsBadge"
import { RecordServerDisplay } from "@/components/Records/RecordServerDisplay"
import { ReplayAvailabilityButton } from "@/components/Records/ReplayAvailabilityButton"
import { TeleportsBadge } from "@/components/Records/TeleportsBadge"
import { formatRecordTime } from "@/components/Records/utils"
import { ReportPlayerDialog } from "@/components/Reports/ReportPlayerDialog"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { isLoggedIn } from "@/hooks/useAuth"
import { getLocale } from "@/i18n/locale"
import { cn } from "@/lib/utils"

type MapTopTableRow = {
  rank: number
  record: RecordPublic
}

function getWrGap(recordTime: number, wrTime: number | null): number | null {
  if (wrTime === null || !Number.isFinite(wrTime) || wrTime <= 0) {
    return null
  }

  const ratioDelta = recordTime / wrTime - 1
  if (!Number.isFinite(ratioDelta) || ratioDelta <= 0) {
    return null
  }

  const wrGap = Math.log2(ratioDelta)
  return Number.isFinite(wrGap) ? wrGap : null
}

function WrGapHeader() {
  const { t } = useTranslation()

  return (
    <div className="flex items-center justify-end gap-1">
      <span>{t("labels.wrGap")}</span>
      <Dialog>
        <DialogTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="size-6 text-muted-foreground hover:text-foreground"
            aria-label={t("maps.wrGapInfoButtonAria")}
          >
            <InfoIcon className="size-3.5" />
          </Button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("maps.wrGapInfoTitle")}</DialogTitle>
            <DialogDescription>
              {t("maps.wrGapInfoDescription")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm leading-relaxed text-foreground/90">
            <div className="rounded-lg border border-border/70 bg-muted/35 p-3">
              <p className="font-medium">{t("maps.wrGapInfoFormulaLabel")}</p>
              <p className="font-mono text-sm">
                log2(record.time / wr.time - 1)
              </p>
            </div>
            <p>{t("maps.wrGapInfoCloser")}</p>
            <div className="rounded-lg border border-border/70 bg-muted/35 p-3">
              <p className="font-medium">{t("maps.wrGapInfoExampleLabel")}</p>
              <p>{t("maps.wrGapInfoExample")}</p>
            </div>
            <p className="text-muted-foreground">{t("maps.wrGapInfoWrRow")}</p>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export function MapTopTable({
  records,
  wrTime,
  emptyMessage,
  isLoading,
  pageIndex,
  pageSize,
  totalCount,
  onPageChange,
  onPageSizeChange,
  currentUserSteamid64,
  renderAdminActions,
  getRowContextMenu,
}: {
  records: RecordPublic[]
  wrTime: number | null
  emptyMessage: string
  isLoading: boolean
  pageIndex: number
  pageSize: number
  totalCount: number
  onPageChange: (pageIndex: number) => void
  onPageSizeChange: (pageSize: number) => void
  currentUserSteamid64: string | null
  renderAdminActions?: (record: RecordPublic) => ReactNode
  getRowContextMenu?: (record: RecordPublic) => ReactNode
}) {
  const { t } = useTranslation()
  const [reportRecord, setReportRecord] = useState<RecordPublic | null>(null)
  const authenticated = isLoggedIn()
  const wrGapFormatter = useMemo(
    () =>
      new Intl.NumberFormat(getLocale(), {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    [],
  )

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
        size: 96,
        header: () => t("labels.rank"),
        cell: ({ row }) => (
          <span className="font-mono font-semibold text-foreground/90">
            #{row.original.rank}
          </span>
        ),
      },
      {
        id: "player",
        size: 300,
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
        size: 96,
        header: () => t("labels.mode"),
        cell: ({ row }) => <ModeBadge mode={row.original.record.mode} />,
      },
      {
        id: "tps",
        size: 96,
        header: () => t("labels.tps"),
        cell: ({ row }) => (
          <TeleportsBadge teleports={row.original.record.teleports} />
        ),
      },
      {
        id: "time",
        size: 148,
        meta: {
          headerClassName: "text-right",
          cellClassName: "text-right",
        },
        header: () => <div className="text-right">{t("labels.time")}</div>,
        cell: ({ row }) => (
          <div className="text-right font-mono font-medium">
            {formatRecordTime(row.original.record.time)}
          </div>
        ),
      },
      {
        id: "wrGap",
        size: 112,
        meta: {
          headerClassName: "text-right",
          cellClassName: "text-right",
        },
        header: () => <WrGapHeader />,
        cell: ({ row }) => {
          const wrGap = getWrGap(row.original.record.time, wrTime)
          return (
            <div className="text-right font-mono font-medium text-foreground/90">
              {wrGap === null ? "-" : wrGapFormatter.format(wrGap)}
            </div>
          )
        },
      },
      {
        id: "points",
        size: 112,
        header: () => t("labels.points"),
        cell: ({ row }) => <PointsBadge points={row.original.record.points} />,
      },
      {
        id: "server",
        size: 320,
        header: () => t("labels.server"),
        cell: ({ row }) => (
          <RecordServerDisplay
            serverName={row.original.record.server_name}
            serverGroup={row.original.record.server_group}
          />
        ),
      },
      {
        id: "datetime",
        size: 176,
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
      {
        id: "replay",
        size: 40,
        meta: {
          headerClassName: "!px-2",
          cellClassName: "!px-2",
        },
        header: () => (
          <div className="flex w-6 justify-center">
            <span className="sr-only">Replay</span>
          </div>
        ),
        cell: ({ row }) => (
          <div className="flex w-6 justify-center">
            <ReplayAvailabilityButton record={row.original.record} />
          </div>
        ),
      },
      ...(renderAdminActions
        ? [
            {
              id: "actions",
              size: 56,
              meta: {
                headerClassName: "!px-2",
                cellClassName: "!px-2",
              },
              header: () => <span className="sr-only">Actions</span>,
              cell: ({ row }: { row: { original: MapTopTableRow } }) => (
                <div className="flex justify-center">
                  {renderAdminActions(row.original.record)}
                </div>
              ),
            } satisfies ColumnDef<MapTopTableRow>,
          ]
        : []),
    ],
    [renderAdminActions, t, wrGapFormatter, wrTime],
  )

  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize))
  const getReportAwareRowContextMenu = (record: RecordPublic) => {
    const rowActionContent = getRowContextMenu?.(record) ?? null
    const canReportRecord = authenticated
    if (!canReportRecord && !rowActionContent) {
      return null
    }

    return (
      <>
        {canReportRecord ? (
          <RowContextMenuItem
            data-testid="report-record-menu-item"
            variant="destructive"
            onSelect={() => {
              setReportRecord(record)
            }}
          >
            <Flag />
            Report
          </RowContextMenuItem>
        ) : null}
        {canReportRecord && rowActionContent ? (
          <RowContextMenuSeparator />
        ) : null}
        {rowActionContent}
      </>
    )
  }

  return (
    <>
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
            tableClassName="table-fixed border-separate border-spacing-0"
            showFooter={false}
            getRowContextMenu={(row) =>
              getReportAwareRowContextMenu(row.record)
            }
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
      {reportRecord ? (
        <ReportPlayerDialog
          open={reportRecord !== null}
          onOpenChange={(open) => {
            if (!open) {
              setReportRecord(null)
            }
          }}
          target={{
            steamid64: reportRecord.player.steamid64,
            displayName: reportRecord.player.display_name,
          }}
          recordContext={{
            uuid: reportRecord.uuid,
            mapName: reportRecord.map_name,
            time: reportRecord.time,
            createdOn: reportRecord.created_on,
          }}
        />
      ) : null}
    </>
  )
}
