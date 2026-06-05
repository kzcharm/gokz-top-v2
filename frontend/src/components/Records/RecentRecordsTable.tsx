import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"
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

import { ModeBadge } from "./ModeBadge"
import { PointsBadge } from "./PointsBadge"
import { StageBadge } from "./StageBadge"
import { TeleportsBadge } from "./TeleportsBadge"
import { formatRecordTime, type RecentRecord } from "./utils"

interface RecentRecordsTableProps {
  records: RecentRecord[]
  renderAdminActions?: (record: RecentRecord) => ReactNode
}

export function RecentRecordsTable({
  records,
  renderAdminActions,
}: RecentRecordsTableProps) {
  const { t } = useTranslation()
  const tableHeadClassName = "normal-case tracking-normal text-foreground/80"

  return (
    <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className={`min-w-56 ${tableHeadClassName}`}>
                {t("labels.player")}
              </TableHead>
              <TableHead className={`min-w-60 ${tableHeadClassName}`}>
                {t("labels.map")}
              </TableHead>
              <TableHead className={`min-w-20 ${tableHeadClassName}`}>
                {t("labels.mode")}
              </TableHead>
              <TableHead className={`min-w-28 ${tableHeadClassName}`}>
                Stage
              </TableHead>
              <TableHead className={`min-w-20 ${tableHeadClassName}`}>
                {t("labels.tier")}
              </TableHead>
              <TableHead className={`min-w-20 ${tableHeadClassName}`}>
                {t("labels.tps")}
              </TableHead>
              <TableHead
                className={`min-w-24 text-right ${tableHeadClassName}`}
              >
                {t("labels.time")}
              </TableHead>
              <TableHead className={`min-w-24 ${tableHeadClassName}`}>
                {t("labels.points")}
              </TableHead>
              <TableHead className={`min-w-44 ${tableHeadClassName}`}>
                {t("labels.server")}
              </TableHead>
              <TableHead className={`min-w-32 ${tableHeadClassName}`}>
                {t("labels.datetime")}
              </TableHead>
              {renderAdminActions ? (
                <TableHead className={`w-14 px-2 ${tableHeadClassName}`}>
                  <span className="sr-only">Actions</span>
                </TableHead>
              ) : null}
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
                    <MapDisplay
                      mapName={record.map.name}
                      mapId={record.map.id}
                    />
                  </TableCell>
                  <TableCell>
                    <ModeBadge mode={record.mode.name} />
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
                  <TableCell className="text-right font-mono font-medium">
                    {formatRecordTime(record.time)}
                  </TableCell>
                  <TableCell>
                    <PointsBadge points={record.points} />
                  </TableCell>
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
                  {renderAdminActions ? (
                    <TableCell className="w-14 px-2">
                      <div className="flex justify-center">
                        {renderAdminActions(record)}
                      </div>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={renderAdminActions ? 11 : 10}
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
