import { ArrowDown, ArrowUp } from "lucide-react"
import type { KeyboardEvent, MouseEvent, ReactNode } from "react"
import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import type { RecordPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { DateTimeDisplay } from "@/lib/date-time"
import { cn, truncateText } from "@/lib/utils"
import { ModeBadge } from "./ModeBadge"
import { PointsBadge } from "./PointsBadge"
import type { PbRecordsColumn, PbRecordsSortState } from "./pb-records-utils"
import { ReplayAvailabilityButton } from "./ReplayAvailabilityButton"
import { TeleportsBadge } from "./TeleportsBadge"
import { formatRecordTime } from "./utils"

interface PbRecordsTableProps {
  records: RecordPublic[]
  columns?: PbRecordsColumn[]
  columnFilters?: Partial<Record<PbRecordsColumn, ReactNode>>
  emptyMessage?: string
  dateTimeDisplay?: DateTimeDisplay
  sort?: PbRecordsSortState
  onSortChange?: (column: PbRecordsColumn) => void
  getRowContextMenu?: (record: RecordPublic) => ReactNode
  getMapContextMenu?: (record: RecordPublic) => ReactNode
  showReplayColumn?: boolean
  renderAdminActions?: (record: RecordPublic) => ReactNode
}

function PbRecordTableRow({
  dateTimeDisplay,
  getMapContextMenu,
  getRowContextMenu,
  record,
  showReplayColumn,
  visibleColumns,
  renderAdminActions,
}: {
  dateTimeDisplay: DateTimeDisplay
  getMapContextMenu?: (record: RecordPublic) => ReactNode
  getRowContextMenu?: (record: RecordPublic) => ReactNode
  record: RecordPublic
  renderAdminActions?: (record: RecordPublic) => ReactNode
  showReplayColumn: boolean
  visibleColumns: Set<PbRecordsColumn>
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const contextMenuRequestedRef = useRef(false)
  const menuContent = getRowContextMenu?.(record) ?? null

  const row = (
    <TableRow
      data-testid={`pb-record-row-${record.uuid}`}
      className={cn(menuContent && "outline-none")}
      onContextMenu={
        menuContent
          ? (event: MouseEvent<HTMLTableRowElement>) => {
              event.preventDefault()
              contextMenuRequestedRef.current = true
              setMenuOpen(true)
            }
          : undefined
      }
      onKeyDown={
        menuContent
          ? (event: KeyboardEvent<HTMLTableRowElement>) => {
              if (
                event.key === "ContextMenu" ||
                (event.shiftKey && event.key === "F10")
              ) {
                event.preventDefault()
                contextMenuRequestedRef.current = true
                setMenuOpen(true)
              }
            }
          : undefined
      }
      tabIndex={menuContent ? 0 : undefined}
    >
      {visibleColumns.has("player") ? (
        <TableCell>
          <PlayerDisplay
            player={record.player}
            className="max-w-[15rem]"
            nameMaxLength={24}
          />
        </TableCell>
      ) : null}
      {visibleColumns.has("map") ? (
        <TableCell>
          <MapDisplay
            mapName={record.map_name}
            mapId={record.map_id}
            contextMenuItems={getMapContextMenu?.(record) ?? null}
          />
        </TableCell>
      ) : null}
      {visibleColumns.has("mode") ? (
        <TableCell>
          <ModeBadge mode={record.mode} />
        </TableCell>
      ) : null}
      {visibleColumns.has("tier") ? (
        <TableCell>
          <TierBadge tier={record.map_tier} hideWhenUnknown />
        </TableCell>
      ) : null}
      {visibleColumns.has("tps") ? (
        <TableCell>
          <TeleportsBadge teleports={record.teleports} />
        </TableCell>
      ) : null}
      {visibleColumns.has("time") ? (
        <TableCell className="text-right font-mono font-medium">
          {formatRecordTime(record.time)}
        </TableCell>
      ) : null}
      {visibleColumns.has("points") ? (
        <TableCell>
          <PointsBadge points={record.points} />
        </TableCell>
      ) : null}
      {visibleColumns.has("server") ? (
        <TableCell className="text-sm text-foreground/90">
          <span
            className="block max-w-[14rem] truncate"
            title={record.server_name}
          >
            {truncateText(record.server_name, 32)}
          </span>
        </TableCell>
      ) : null}
      {visibleColumns.has("datetime") ? (
        <TableCell className="text-sm text-muted-foreground">
          <FormattedDateTime
            value={record.created_on}
            display={dateTimeDisplay}
            fallback="-"
          />
        </TableCell>
      ) : null}
      {showReplayColumn ? (
        <TableCell className="w-10 px-2">
          <div className="flex justify-center">
            <ReplayAvailabilityButton record={record} />
          </div>
        </TableCell>
      ) : null}
      {renderAdminActions ? (
        <TableCell className="w-14 px-2">
          <div className="flex justify-center">
            {renderAdminActions(record)}
          </div>
        </TableCell>
      ) : null}
    </TableRow>
  )

  if (menuContent === null) {
    return row
  }

  return (
    <DropdownMenu
      modal={false}
      open={menuOpen}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          contextMenuRequestedRef.current = false
          setMenuOpen(false)
          return
        }

        if (contextMenuRequestedRef.current) {
          setMenuOpen(true)
        }
      }}
    >
      <DropdownMenuTrigger asChild>{row}</DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="bottom" sideOffset={8}>
        {menuContent}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function SortableHeader({
  column,
  label,
  sort,
  onSortChange,
  className,
}: {
  column: PbRecordsColumn
  label: string
  sort?: PbRecordsSortState
  onSortChange?: (column: PbRecordsColumn) => void
  className?: string
}) {
  const isActive = sort?.column === column
  const direction = isActive ? sort.direction : null

  if (!onSortChange) {
    return <span className={className}>{label}</span>
  }

  return (
    <Button
      type="button"
      variant="ghost"
      className={`-ml-3 h-8 px-3 text-left ${className ?? ""}`}
      onClick={() => onSortChange(column)}
    >
      <span>{label}</span>
      {direction === "asc" ? (
        <ArrowUp className="ml-2 size-4" />
      ) : direction === "desc" ? (
        <ArrowDown className="ml-2 size-4" />
      ) : null}
    </Button>
  )
}

export function PbRecordsTable({
  records,
  columns = [
    "player",
    "map",
    "mode",
    "tier",
    "tps",
    "time",
    "points",
    "server",
    "datetime",
  ],
  columnFilters,
  emptyMessage = "No records found.",
  dateTimeDisplay = "relative",
  sort,
  onSortChange,
  getRowContextMenu,
  getMapContextMenu,
  showReplayColumn = false,
  renderAdminActions,
}: PbRecordsTableProps) {
  const { t } = useTranslation()
  const visibleColumns = new Set(columns)
  const tableHeadClassName = "normal-case tracking-normal text-foreground/80"
  const colSpan =
    columns.length + (showReplayColumn ? 1 : 0) + (renderAdminActions ? 1 : 0)
  const hasColumnFilters = columns.some(
    (column) => columnFilters?.[column] !== undefined,
  )

  return (
    <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {visibleColumns.has("player") ? (
                <TableHead className={`min-w-56 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="player"
                    label={t("labels.player")}
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("map") ? (
                <TableHead className={`min-w-60 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="map"
                    label={t("labels.map")}
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("mode") ? (
                <TableHead className={`min-w-14 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="mode"
                    label={t("labels.mode")}
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("tier") ? (
                <TableHead className={`min-w-14 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="tier"
                    label={t("labels.tier")}
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("tps") ? (
                <TableHead className={`min-w-14 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="tps"
                    label={t("labels.tps")}
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("time") ? (
                <TableHead
                  className={`min-w-24 text-right ${tableHeadClassName}`}
                >
                  <SortableHeader
                    column="time"
                    label={t("labels.time")}
                    sort={sort}
                    onSortChange={onSortChange}
                    className={`justify-end ${tableHeadClassName}`}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("points") ? (
                <TableHead className={`min-w-24 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="points"
                    label={t("labels.points")}
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("server") ? (
                <TableHead className={`min-w-44 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="server"
                    label={t("labels.server")}
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("datetime") ? (
                <TableHead className={`min-w-32 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="datetime"
                    label={t("labels.datetime")}
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {showReplayColumn ? (
                <TableHead className={`w-10 px-2 ${tableHeadClassName}`}>
                  <span className="sr-only">Replay</span>
                </TableHead>
              ) : null}
              {renderAdminActions ? (
                <TableHead className={`w-14 px-2 ${tableHeadClassName}`}>
                  <span className="sr-only">Actions</span>
                </TableHead>
              ) : null}
            </TableRow>
            {hasColumnFilters ? (
              <TableRow className="hover:bg-transparent">
                {columns.map((column) => {
                  const filterCell = (
                    <TableHead
                      key={`filter-${column}`}
                      className="h-auto border-t border-border/60 px-3 py-3 align-top"
                    >
                      {columnFilters?.[column] ?? null}
                    </TableHead>
                  )

                  if (column === "datetime" && showReplayColumn) {
                    return [
                      filterCell,
                      <TableHead
                        key="filter-replay"
                        className="h-auto w-10 border-t border-border/60 px-2 py-3 align-top"
                      />,
                      ...(renderAdminActions
                        ? [
                            <TableHead
                              key="filter-actions"
                              className="h-auto w-14 border-t border-border/60 px-2 py-3 align-top"
                            />,
                          ]
                        : []),
                    ]
                  }

                  return filterCell
                })}
                {!columns.includes("datetime") && renderAdminActions ? (
                  <TableHead className="h-auto w-14 border-t border-border/60 px-2 py-3 align-top" />
                ) : null}
              </TableRow>
            ) : null}
          </TableHeader>
          <TableBody>
            {records.length > 0 ? (
              records.map((record) => (
                <PbRecordTableRow
                  key={record.uuid}
                  dateTimeDisplay={dateTimeDisplay}
                  getMapContextMenu={getMapContextMenu}
                  getRowContextMenu={getRowContextMenu}
                  record={record}
                  renderAdminActions={renderAdminActions}
                  showReplayColumn={showReplayColumn}
                  visibleColumns={visibleColumns}
                />
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={colSpan}
                  className="h-32 text-center text-muted-foreground"
                >
                  {emptyMessage}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
