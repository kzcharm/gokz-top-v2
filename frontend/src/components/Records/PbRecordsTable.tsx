import { ArrowDown, ArrowUp } from "lucide-react"

import type { RecordPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { DateTimeDisplay } from "@/lib/date-time"
import { truncateText } from "@/lib/utils"
import { ModeBadge } from "./ModeBadge"
import { PointsBadge } from "./PointsBadge"
import { TeleportsBadge } from "./TeleportsBadge"
import { formatRecordTime } from "./utils"

export type PbRecordsColumn =
  | "player"
  | "map"
  | "mode"
  | "tier"
  | "tps"
  | "time"
  | "points"
  | "server"
  | "datetime"

export type PbRecordsSortDirection = "asc" | "desc"

export interface PbRecordsSortState {
  column: PbRecordsColumn
  direction: PbRecordsSortDirection
}

interface PbRecordsTableProps {
  records: RecordPublic[]
  columns?: PbRecordsColumn[]
  emptyMessage?: string
  dateTimeDisplay?: DateTimeDisplay
  sort?: PbRecordsSortState
  onSortChange?: (column: PbRecordsColumn) => void
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
  emptyMessage = "No records found.",
  dateTimeDisplay = "relative",
  sort,
  onSortChange,
}: PbRecordsTableProps) {
  const visibleColumns = new Set(columns)
  const tableHeadClassName = "normal-case tracking-normal text-foreground/80"
  const colSpan = columns.length

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
                    label="Player"
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
                    label="Map"
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("mode") ? (
                <TableHead className={`min-w-20 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="mode"
                    label="Mode"
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("tier") ? (
                <TableHead className={`min-w-20 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="tier"
                    label="Tier"
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
              {visibleColumns.has("tps") ? (
                <TableHead className={`min-w-20 ${tableHeadClassName}`}>
                  <SortableHeader
                    column="tps"
                    label="TPs"
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
                    label="Time"
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
                    label="Points"
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
                    label="Server"
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
                    label="Datetime"
                    sort={sort}
                    onSortChange={onSortChange}
                    className={tableHeadClassName}
                  />
                </TableHead>
              ) : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {records.length > 0 ? (
              records.map((record) => (
                <TableRow
                  key={record.uuid}
                  data-testid={`pb-record-row-${record.uuid}`}
                >
                  {visibleColumns.has("player") ? (
                    <TableCell>
                      <PlayerDisplay
                        player={{
                          steamid64: record.steamid64,
                          name: record.player_name,
                          avatar_hash: record.player_avatar_hash,
                        }}
                        className="max-w-[15rem]"
                        nameMaxLength={24}
                      />
                    </TableCell>
                  ) : null}
                  {visibleColumns.has("map") ? (
                    <TableCell>
                      <MapDisplay mapName={record.map_name} />
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
                </TableRow>
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
