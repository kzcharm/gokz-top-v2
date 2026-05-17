import { useQuery } from "@tanstack/react-query"
import { TriangleAlertIcon } from "lucide-react"
import { useTranslation } from "react-i18next"

import {
  type JumpstatDetailPublic,
  JumpstatsService,
  type JumpstatType,
  type JumpstatVisualizationPublic,
} from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { JumpstatRouteVisualization } from "@/components/Leaderboards/JumpstatRouteVisualization"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Dialog, DialogContent, DialogHeader } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { extractErrorMessage } from "@/utils"

function formatDecimal(value: number, digits = 1) {
  return value.toFixed(digits)
}

function formatJumpstatType(value: JumpstatType) {
  const labels: Record<JumpstatType, string> = {
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

function padCell(value: string, width: number, align: "start" | "end" = "end") {
  return align === "start"
    ? value.padEnd(width, " ")
    : value.padStart(width, " ")
}

function buildConsoleBlock(jumpstat: JumpstatDetailPublic) {
  const lines = [
    `${jumpstat.player.display_name} jumped ${formatDecimal(jumpstat.distance, 4)} units with a ${formatJumpstatType(jumpstat.type)}`,
    [
      jumpstat.mode,
      `${jumpstat.strafes} Strafes`,
      `${jumpstat.sync_percent}% Sync`,
      `${formatDecimal(jumpstat.pre_speed, 2)} Pre`,
      `${formatDecimal(jumpstat.max_speed, 2)} Max`,
      `${jumpstat.w_count} W`,
      `${jumpstat.overlap_count} OL`,
      `${jumpstat.dead_air_count} DA`,
      `${formatDecimal(jumpstat.width, 1)}° Width`,
      `${formatDecimal(jumpstat.height, 1)} Height`,
      `${jumpstat.airtime_percent} Airtime`,
      `${formatDecimal(jumpstat.offset, 1)} Offset`,
      `${jumpstat.crouched_ticks} Crouched`,
    ].join(" | "),
    "",
    [
      `${padCell("#.", 4, "start")}`,
      `${padCell("Sync", 6, "start")}`,
      `${padCell("Gain", 9, "start")}`,
      `${padCell("Loss", 9, "start")}`,
      `${padCell("Airtime", 9, "start")}`,
      `${padCell("Width", 8, "start")}`,
      `${padCell("OL", 4, "start")}`,
      `${padCell("DA", 4, "start")}`,
    ].join("  "),
    ...jumpstat.strafe_stats.map((strafe) =>
      [
        `${padCell(`${strafe.index}.`, 4)}`,
        `${padCell(`${strafe.sync_percent}%`, 6)}`,
        `${padCell(formatDecimal(strafe.gain, 2), 9)}`,
        `${padCell(formatDecimal(strafe.loss, 2), 9)}`,
        `${padCell(`${strafe.airtime_percent}%`, 9)}`,
        `${padCell(`${formatDecimal(strafe.width, 1)}°`, 8)}`,
        `${padCell(String(strafe.overlap_count), 4)}`,
        `${padCell(String(strafe.dead_air_count), 4)}`,
      ].join("  "),
    ),
  ]

  return lines.join("\n")
}

function JumpstatDetailPanel({
  jumpstat,
  visualization,
  visualizationLoading,
}: {
  jumpstat: JumpstatDetailPublic
  visualization: JumpstatVisualizationPublic | undefined
  visualizationLoading: boolean
}) {
  const { t } = useTranslation()
  const consoleBlock = buildConsoleBlock(jumpstat)

  return (
    <div className="space-y-6">
      <div className="rounded-[26px] border border-border/70 bg-card/95 p-5">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <div className="text-[11px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Player
            </div>
            <div className="mt-2 flex min-h-10 items-center">
              <PlayerDisplay player={jumpstat.player} />
            </div>
          </div>
          <div>
            <div className="text-[11px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Distance
            </div>
            <div className="mt-2 flex min-h-10 items-center font-mono text-sm text-foreground">
              {formatDecimal(jumpstat.distance, 4)}{" "}
              {t("leaderboards.jumpstats.dialog.units")}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Server
            </div>
            <div className="mt-2 flex min-h-10 items-center text-sm text-foreground">
              {jumpstat.server_group.name}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Jumped At
            </div>
            <div className="mt-2 flex min-h-10 items-center text-sm text-foreground">
              <FormattedDateTime
                value={jumpstat.jumped_at}
                display="absolute"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-[26px] border border-[#5d5d5d] bg-[#3b3b3b] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
        <div>
          <pre className="whitespace-pre-wrap break-words font-mono text-[13px] leading-7 text-[#d4d4d4]">
            {consoleBlock}
          </pre>
          {visualization ? (
            <div className="mt-4 font-mono text-xs text-[#b7b7b7]">
              {t("leaderboards.jumpstats.dialog.visualization.deviationAngle")}:{" "}
              {formatDecimal(visualization.deviation_angle, 2)}°
            </div>
          ) : null}
        </div>
      </div>

      {visualizationLoading ? (
        <Skeleton className="h-[28rem] w-full rounded-[26px]" />
      ) : null}

      {!visualizationLoading && visualization ? (
        <JumpstatRouteVisualization
          visualization={visualization}
          title={t("leaderboards.jumpstats.dialog.visualization.title")}
          deviationLabel={t(
            "leaderboards.jumpstats.dialog.visualization.deviationAngle",
          )}
          legendLabel={t("leaderboards.jumpstats.dialog.visualization.legend")}
          neutralLabel={t(
            "leaderboards.jumpstats.dialog.visualization.neutral",
          )}
          gainLabel={t("leaderboards.jumpstats.dialog.visualization.gain")}
          lossLabel={t("leaderboards.jumpstats.dialog.visualization.loss")}
          duckLabel={t("leaderboards.jumpstats.dialog.visualization.duck")}
          aLabel={t("leaderboards.jumpstats.dialog.visualization.aKey")}
          dLabel={t("leaderboards.jumpstats.dialog.visualization.dKey")}
          mouseLabel={t("leaderboards.jumpstats.dialog.visualization.mouse")}
        />
      ) : null}
    </div>
  )
}

function JumpstatDialogSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-36 w-full rounded-[26px]" />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <Skeleton className="h-[28rem] w-full rounded-[26px]" />
        <Skeleton className="h-[28rem] w-full rounded-[26px]" />
      </div>
    </div>
  )
}

export function JumpstatDetailsDialog({
  jumpstatId,
  open,
  onOpenChange,
}: {
  jumpstatId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()

  const detailQuery = useQuery({
    queryKey: ["jumpstat-detail", jumpstatId],
    queryFn: () =>
      JumpstatsService.readJumpstat({ jumpstatId: jumpstatId ?? "" }),
    enabled: open && jumpstatId !== null,
    staleTime: 30_000,
  })

  const visualizationQuery = useQuery({
    queryKey: ["jumpstat-visualization", jumpstatId],
    queryFn: () =>
      JumpstatsService.readJumpstatVisualization({
        jumpstatId: jumpstatId ?? "",
      }),
    enabled: open && jumpstatId !== null,
    retry: false,
    staleTime: 30_000,
  })

  const loading = detailQuery.isLoading
  const detail = detailQuery.data

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto rounded-[30px] border-border/70 p-0 sm:max-w-6xl">
        <DialogHeader className="sr-only" />

        <div className="px-6 pt-6 pb-6 sm:px-8 sm:pt-8 sm:pb-8">
          {loading ? <JumpstatDialogSkeleton /> : null}

          {!loading && detailQuery.isError ? (
            <Alert variant="destructive">
              <TriangleAlertIcon />
              <AlertTitle>
                {t("leaderboards.jumpstats.dialog.detailLoadFailedTitle")}
              </AlertTitle>
              <AlertDescription>
                {extractErrorMessage(detailQuery.error) ||
                  t("leaderboards.jumpstats.dialog.detailLoadFailedBody")}
              </AlertDescription>
            </Alert>
          ) : null}

          {!loading && detail ? (
            <div className="space-y-6">
              {visualizationQuery.isError ? (
                <Alert variant="destructive">
                  <TriangleAlertIcon />
                  <AlertTitle>
                    {t(
                      "leaderboards.jumpstats.dialog.visualizationLoadFailedTitle",
                    )}
                  </AlertTitle>
                  <AlertDescription>
                    {extractErrorMessage(visualizationQuery.error) ||
                      t(
                        "leaderboards.jumpstats.dialog.visualizationLoadFailedBody",
                      )}
                  </AlertDescription>
                </Alert>
              ) : null}

              <JumpstatDetailPanel
                jumpstat={detail}
                visualization={visualizationQuery.data}
                visualizationLoading={visualizationQuery.isLoading}
              />
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  )
}
