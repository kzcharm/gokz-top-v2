import { Gauge, Ruler, StepForward, TriangleAlertIcon } from "lucide-react"
import { useTranslation } from "react-i18next"

import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import type {
  ProfileJumpstatDetail,
  ProfileJumpstatsResult,
} from "./profile-utils"

function formatDecimal(value: number, digits = 1) {
  return value.toFixed(digits)
}

function formatJumpstatType(value: string) {
  const labels: Record<string, string> = {
    LJ: "Long Jump",
    BH: "Bhop",
    MBH: "Multi Bunnyhop",
    WJ: "Weird Jump",
    LAJ: "Ladder Jump",
    LAH: "Ladderhop",
    JB: "Jumpbug",
    LBH: "Ladder Bunnyhop",
    LWJ: "Ladder Weird Jump",
    FL: "Fall",
    UNK: "Unknown",
    INV: "Invalid",
  }
  return labels[value] ?? value
}

function JumpstatSummaryPill({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background/70 px-3 py-2">
      <div className="text-[10px] font-semibold tracking-[0.16em] text-muted-foreground uppercase">
        {label}
      </div>
      <div className="mt-1 font-mono text-sm font-semibold tabular-nums">
        {value}
      </div>
    </div>
  )
}

function JumpstatCard({ jumpstat }: { jumpstat: ProfileJumpstatDetail }) {
  const { t } = useTranslation()
  const typeLabel = formatJumpstatType(jumpstat.type)

  return (
    <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant="outline"
                className="border-sky-300/60 bg-sky-500/10 text-sky-700 dark:border-sky-500/30 dark:text-sky-300"
              >
                {jumpstat.mode}
              </Badge>
              {jumpstat.block !== null ? (
                <Badge variant="outline" className="font-mono tabular-nums">
                  {jumpstat.block} Block
                </Badge>
              ) : null}
              <Badge variant="outline">{typeLabel}</Badge>
            </div>
            <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
              <div className="font-mono text-3xl font-semibold tabular-nums tracking-tight">
                {formatDecimal(jumpstat.distance, 4)}
              </div>
              <div className="pb-1 text-sm text-muted-foreground">
                {t("profile.jumpstats.units")}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <span>{jumpstat.server_group.name}</span>
              <span>•</span>
              <FormattedDateTime
                value={jumpstat.jumped_at}
                display="absolute"
              />
            </div>
          </div>

          <div className="grid min-w-0 grid-cols-2 gap-3 sm:grid-cols-4">
            <JumpstatSummaryPill
              label={t("profile.jumpstats.summary.strafes")}
              value={String(jumpstat.strafes)}
            />
            <JumpstatSummaryPill
              label={t("profile.jumpstats.summary.sync")}
              value={`${jumpstat.sync_percent}%`}
            />
            <JumpstatSummaryPill
              label={t("profile.jumpstats.summary.pre")}
              value={formatDecimal(jumpstat.pre_speed, 2)}
            />
            <JumpstatSummaryPill
              label={t("profile.jumpstats.summary.max")}
              value={formatDecimal(jumpstat.max_speed, 2)}
            />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <JumpstatSummaryPill
            label={t("profile.jumpstats.summary.width")}
            value={`${formatDecimal(jumpstat.width, 1)}°`}
          />
          <JumpstatSummaryPill
            label={t("profile.jumpstats.summary.height")}
            value={formatDecimal(jumpstat.height, 1)}
          />
          <JumpstatSummaryPill
            label={t("profile.jumpstats.summary.airtime")}
            value={`${jumpstat.airtime_percent}%`}
          />
          <JumpstatSummaryPill
            label={t("profile.jumpstats.summary.offset")}
            value={formatDecimal(jumpstat.offset, 1)}
          />
          <JumpstatSummaryPill
            label={t("profile.jumpstats.summary.w")}
            value={String(jumpstat.w_count)}
          />
          <JumpstatSummaryPill
            label={t("profile.jumpstats.summary.ol")}
            value={String(jumpstat.overlap_count)}
          />
          <JumpstatSummaryPill
            label={t("profile.jumpstats.summary.da")}
            value={String(jumpstat.dead_air_count)}
          />
          <JumpstatSummaryPill
            label={t("profile.jumpstats.summary.crouched")}
            value={String(jumpstat.crouched_ticks)}
          />
        </div>

        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
            <Gauge className="h-4 w-4 text-muted-foreground" />
            <span>{t("profile.jumpstats.breakdownTitle")}</span>
          </div>
          <Table containerClassName="rounded-2xl border-border/70 bg-background/60">
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>{t("profile.jumpstats.table.sync")}</TableHead>
                <TableHead>{t("profile.jumpstats.table.gain")}</TableHead>
                <TableHead>{t("profile.jumpstats.table.loss")}</TableHead>
                <TableHead>{t("profile.jumpstats.table.airtime")}</TableHead>
                <TableHead>{t("profile.jumpstats.table.width")}</TableHead>
                <TableHead>{t("profile.jumpstats.table.ol")}</TableHead>
                <TableHead>{t("profile.jumpstats.table.da")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jumpstat.strafe_stats.map((strafe) => (
                <TableRow key={strafe.index}>
                  <TableCell className="font-mono tabular-nums">
                    {strafe.index}
                  </TableCell>
                  <TableCell className="font-mono tabular-nums">
                    {strafe.sync_percent}%
                  </TableCell>
                  <TableCell className="font-mono tabular-nums">
                    {formatDecimal(strafe.gain, 2)}
                  </TableCell>
                  <TableCell className="font-mono tabular-nums">
                    {formatDecimal(strafe.loss, 2)}
                  </TableCell>
                  <TableCell className="font-mono tabular-nums">
                    {strafe.airtime_percent}%
                  </TableCell>
                  <TableCell className="font-mono tabular-nums">
                    {formatDecimal(strafe.width, 1)}°
                  </TableCell>
                  <TableCell className="font-mono tabular-nums">
                    {strafe.overlap_count}
                  </TableCell>
                  <TableCell className="font-mono tabular-nums">
                    {strafe.dead_air_count}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
            {jumpstat.edge !== null ? (
              <div className="inline-flex items-center gap-2">
                <Ruler className="h-3.5 w-3.5" />
                <span className="font-mono tabular-nums">
                  {t("profile.jumpstats.edge")}:{" "}
                  {formatDecimal(jumpstat.edge, 2)}
                </span>
              </div>
            ) : null}
            {jumpstat.deviation !== null ? (
              <div className="inline-flex items-center gap-2">
                <StepForward className="h-3.5 w-3.5" />
                <span className="font-mono tabular-nums">
                  {t("profile.jumpstats.deviation")}:{" "}
                  {formatDecimal(jumpstat.deviation, 2)}
                </span>
              </div>
            ) : null}
            {jumpstat.edge === null && jumpstat.deviation === null ? (
              <span>{t("profile.jumpstats.mapDependentOmitted")}</span>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function JumpstatsSkeleton() {
  return (
    <div className="space-y-6">
      {Array.from({ length: 2 }).map((_, index) => (
        <Card
          key={index}
          className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0"
        >
          <CardContent className="space-y-5 p-6">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-64 w-full rounded-2xl" />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

export function ProfileJumpstatsTab({
  data,
  loading,
  error,
}: {
  data: ProfileJumpstatsResult | null | undefined
  loading: boolean
  error: boolean
}) {
  const { t } = useTranslation()

  if (loading) {
    return <JumpstatsSkeleton />
  }

  if (error) {
    return (
      <Alert>
        <TriangleAlertIcon />
        <AlertTitle>{t("profile.jumpstats.loadFailedTitle")}</AlertTitle>
        <AlertDescription>
          {t("profile.jumpstats.loadFailedBody")}
        </AlertDescription>
      </Alert>
    )
  }

  if (!data || data.data.length === 0) {
    return (
      <Card className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 text-sm text-muted-foreground">
          {t("profile.jumpstats.empty")}
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {data.data.map((jumpstat) => (
        <JumpstatCard key={jumpstat.id} jumpstat={jumpstat} />
      ))}
    </div>
  )
}
