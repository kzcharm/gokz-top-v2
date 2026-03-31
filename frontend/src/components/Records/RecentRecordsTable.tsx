import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { TierBadge } from "@/components/Servers/TierBadge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { truncateText } from "@/lib/utils"

import { StageBadge } from "./StageBadge"
import { TeleportsBadge } from "./TeleportsBadge"
import { formatRecordTime, type RecentRecord } from "./utils"

interface RecentRecordsTableProps {
  records: RecentRecord[]
}

export function RecentRecordsTable({ records }: RecentRecordsTableProps) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="min-w-56">Player</TableHead>
              <TableHead className="min-w-60">Map</TableHead>
              <TableHead className="min-w-28">Stage</TableHead>
              <TableHead className="min-w-20">Tier</TableHead>
              <TableHead className="min-w-20">TPs</TableHead>
              <TableHead className="min-w-24">Time</TableHead>
              <TableHead className="min-w-24">Points</TableHead>
              <TableHead className="min-w-44">Server</TableHead>
              <TableHead className="min-w-32">Datetime</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {records.length > 0 ? (
              records.map((record) => (
                <TableRow
                  key={record.uuid}
                  data-testid={`recent-record-row-${record.uuid}`}
                >
                  <TableCell>
                    <PlayerDisplay
                      player={record.player}
                      nameMaxLength={24}
                      className="max-w-[15rem]"
                    />
                  </TableCell>
                  <TableCell>
                    <MapDisplay mapName={record.map.name} />
                  </TableCell>
                  <TableCell>
                    <StageBadge stage={record.stage} />
                  </TableCell>
                  <TableCell>
                    <TierBadge tier={record.map.tier} hideWhenUnknown />
                  </TableCell>
                  <TableCell>
                    <TeleportsBadge teleports={record.teleports} />
                  </TableCell>
                  <TableCell className="font-mono font-medium">
                    {formatRecordTime(record.time)}
                  </TableCell>
                  <TableCell className="font-medium">{record.points}</TableCell>
                  <TableCell className="text-sm text-foreground/90">
                    <span
                      className="block max-w-[14rem] truncate"
                      title={record.server.name}
                    >
                      {truncateText(record.server.name, 32)}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    <FormattedDateTime
                      value={record.created_on}
                      display="relative"
                      fallback="-"
                    />
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={9}
                  className="h-32 text-center text-muted-foreground"
                >
                  No recent records yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
