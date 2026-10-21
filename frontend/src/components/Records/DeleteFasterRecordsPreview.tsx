import { ChevronRight } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import type {
  RecordBulkDeleteFasterPreview,
  RecordBulkDeleteFasterPreviewPlayer,
} from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatRecordTime } from "./utils"

export function DeleteFasterRecordsPreview({
  preview,
}: {
  preview: RecordBulkDeleteFasterPreview
}) {
  const { t } = useTranslation()
  return (
    <section
      aria-label={t("recordModeration.previewTitle")}
      className="flex min-h-0 flex-col gap-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-medium">{t("recordModeration.previewTitle")}</h3>
        <span className="text-muted-foreground text-sm">
          {t("recordModeration.previewTotal", {
            records: preview.count,
            players: preview.players.length,
          })}
        </span>
      </div>
      {preview.count === 0 ? (
        <p className="text-muted-foreground text-sm">
          {t("recordModeration.previewEmpty")}
        </p>
      ) : (
        <div className="flex max-h-[45vh] flex-col gap-2 overflow-y-auto">
          {preview.players.map((group) => (
            <PlayerPreviewGroup
              key={`${preview.preview_token}:${group.player.steamid64}`}
              {...group}
            />
          ))}
        </div>
      )}
    </section>
  )
}

function PlayerPreviewGroup({
  player,
  records,
}: RecordBulkDeleteFasterPreviewPlayer) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const first = records[0]
  const last = records[records.length - 1]
  return (
    <details
      className="group rounded-lg border"
      onToggle={(event) => setExpanded(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none items-center gap-3 p-3 [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-4 shrink-0 transition-transform group-open:rotate-90" />
        <div className="min-w-0 flex-1">
          <PlayerDisplay player={player} showSteamid compact />
        </div>
        <span className="flex shrink-0 flex-col items-end gap-1">
          <Badge variant="secondary">
            {t("recordModeration.previewRuns", {
              count: records.length,
            })}
          </Badge>
          {first && last ? (
            <span className="font-mono text-xs text-muted-foreground">
              {formatRecordTime(first.time)}
              {first.uuid !== last.uuid
                ? ` – ${formatRecordTime(last.time)}`
                : ""}
            </span>
          ) : null}
        </span>
      </summary>
      {expanded ? (
        <div className="px-3 pb-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("labels.time")}</TableHead>
                <TableHead>{t("labels.mode")}</TableHead>
                <TableHead>{t("labels.tps")}</TableHead>
                <TableHead>{t("labels.server")}</TableHead>
                <TableHead>{t("labels.datetime")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((record) => (
                <TableRow key={record.uuid}>
                  <TableCell className="font-mono">
                    {formatRecordTime(record.time)}
                  </TableCell>
                  <TableCell>{record.mode}</TableCell>
                  <TableCell>{record.teleports}</TableCell>
                  <TableCell>{record.server_name}</TableCell>
                  <TableCell className="whitespace-nowrap">
                    <FormattedDateTime
                      value={record.created_on}
                      display="absolute"
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </details>
  )
}
