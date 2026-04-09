import type { RecordPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { ModeBadge } from "@/components/Records/ModeBadge"
import { formatRecordTime } from "@/components/Records/utils"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

export function MapTopTable({
  records,
  emptyMessage,
}: {
  records: RecordPublic[]
  emptyMessage: string
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="min-w-20 normal-case tracking-normal text-foreground/80">
                Rank
              </TableHead>
              <TableHead className="min-w-56 normal-case tracking-normal text-foreground/80">
                Player
              </TableHead>
              <TableHead className="min-w-20 normal-case tracking-normal text-foreground/80">
                Mode
              </TableHead>
              <TableHead className="min-w-24 text-right normal-case tracking-normal text-foreground/80">
                Time
              </TableHead>
              <TableHead className="min-w-32 normal-case tracking-normal text-foreground/80">
                Updated
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {records.length > 0 ? (
              records.map((record, index) => (
                <TableRow
                  key={record.uuid}
                  data-testid={`map-top-row-${record.uuid}`}
                >
                  <TableCell className="font-mono font-semibold text-foreground/90">
                    #{index + 1}
                  </TableCell>
                  <TableCell>
                    <PlayerDisplay
                      player={record.player}
                      className="max-w-[15rem]"
                      nameMaxLength={24}
                    />
                  </TableCell>
                  <TableCell>
                    <ModeBadge mode={record.mode} />
                  </TableCell>
                  <TableCell className="text-right font-mono font-medium">
                    {formatRecordTime(record.time)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    <FormattedDateTime
                      value={record.updated_on}
                      display="contextual-relative"
                      fallback="-"
                    />
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={5}
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
