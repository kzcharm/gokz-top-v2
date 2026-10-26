import { Pause } from "lucide-react"
import { useTranslation } from "react-i18next"

import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { StageBadge } from "@/components/Records/StageBadge"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"

import {
  formatTimerTime,
  getPlayerBooleanValue,
  getPlayerNumberValue,
  getPlayerProgressPercent,
  getPlayerStatusSurfaceClass,
  getPlayerStringValue,
  type ServerPlayer,
  sortPlayersByProgress,
} from "./utils"

export function ServerPlayerList({ players }: { players: ServerPlayer[] }) {
  const { t } = useTranslation()
  const sortedPlayers = sortPlayersByProgress(players)
  const showTimerColumn = sortedPlayers.some(
    (player) => getPlayerNumberValue(player, "timer_time") !== null,
  )
  const showPingColumn = sortedPlayers.some(
    (player) => getPlayerNumberValue(player, "ping_ms") !== null,
  )
  const showProgressColumn = sortedPlayers.some(
    (player) => getPlayerProgressPercent(player) !== null,
  )
  const showStageColumn = sortedPlayers.some(
    (player) => getPlayerNumberValue(player, "stage") !== null,
  )
  const showStatusColumn = sortedPlayers.some(
    (player) => getPlayerStringValue(player, "status") !== null,
  )
  const visibleColumnCount =
    2 +
    (showPingColumn ? 1 : 0) +
    (showTimerColumn ? 1 : 0) +
    (showProgressColumn ? 1 : 0) +
    (showStageColumn ? 1 : 0) +
    (showStatusColumn ? 1 : 0)

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-[20px] border border-border/70 bg-card shadow-sm">
        <Table
          containerClassName="rounded-none border-0 bg-card"
          className="bg-card"
        >
          <TableHeader>
            <TableRow>
              <TableHead>{t("serverBrowser.player")}</TableHead>
              <TableHead>{t("serverBrowser.duration")}</TableHead>
              {showPingColumn ? (
                <TableHead>{t("serverBrowser.ping")}</TableHead>
              ) : null}
              {showStageColumn ? (
                <TableHead>{t("serverBrowser.stage")}</TableHead>
              ) : null}
              {showTimerColumn ? (
                <TableHead>{t("serverBrowser.timer")}</TableHead>
              ) : null}
              {showProgressColumn ? (
                <TableHead>{t("serverBrowser.progress")}</TableHead>
              ) : null}
              {showStatusColumn ? (
                <TableHead>{t("serverBrowser.status")}</TableHead>
              ) : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedPlayers.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={visibleColumnCount}
                  className="h-24 text-center text-muted-foreground"
                >
                  {t("serverBrowser.noPlayers")}
                </TableCell>
              </TableRow>
            ) : (
              sortedPlayers.map((player, index) => {
                const name =
                  getPlayerStringValue(player, "name") ||
                  t("serverBrowser.playerFallback", { number: index + 1 })
                const steamid64 = getPlayerStringValue(player, "steamid64")
                const timerTime = getPlayerNumberValue(player, "timer_time")
                const durationSeconds = getPlayerNumberValue(
                  player,
                  "duration_seconds",
                )
                const pingMs = getPlayerNumberValue(player, "ping_ms")
                const progress = getPlayerProgressPercent(player)
                const stage = getPlayerNumberValue(player, "stage")
                const isPaused = getPlayerBooleanValue(player, "is_paused")
                const { badgeClassName } = getPlayerStatusSurfaceClass(player)
                const rowKey = steamid64 || `${name}-${index}`

                return (
                  <TableRow key={rowKey}>
                    <TableCell>
                      <PlayerDisplay
                        player={{
                          steamid64: steamid64 || "",
                          clan_tag:
                            getPlayerStringValue(player, "clan_tag") ??
                            getPlayerStringValue(player, "tag"),
                          name,
                          avatar_hash: getPlayerStringValue(
                            player,
                            "avatar_hash",
                          ),
                          country: getPlayerStringValue(player, "country"),
                        }}
                        fallbackSteamid64={steamid64 || undefined}
                        className="max-w-[18rem]"
                        nameMaxLength={28}
                        disableProfileLink={!steamid64}
                      />
                    </TableCell>
                    <TableCell>{formatTimerTime(durationSeconds)}</TableCell>
                    {showPingColumn ? (
                      <TableCell>
                        {pingMs !== null ? `${Math.round(pingMs)} ms` : "-"}
                      </TableCell>
                    ) : null}
                    {showStageColumn ? (
                      <TableCell>
                        {stage !== null ? (
                          <StageBadge
                            stage={stage}
                            label={
                              stage === 0
                                ? t("serverBrowser.main")
                                : t("serverBrowser.bonus", { number: stage })
                            }
                          />
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                    ) : null}
                    {showTimerColumn ? (
                      <TableCell>
                        {formatTimerTime(timerTime, { showDecimals: true })}
                        {isPaused ? (
                          <Pause className="ml-1 inline h-3 w-3 align-middle text-muted-foreground" />
                        ) : null}
                      </TableCell>
                    ) : null}
                    {showProgressColumn ? (
                      <TableCell>
                        {progress !== null ? (
                          <span className="text-sm">
                            {progress.toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                    ) : null}
                    {showStatusColumn ? (
                      <TableCell>
                        <Badge className={cn(badgeClassName)}>
                          {t(
                            (
                              {
                                not_started: "serverBrowser.notStarted",
                                in_progress: "serverBrowser.inProgress",
                                finished: "serverBrowser.finished",
                                aborted: "serverBrowser.aborted",
                              } as Record<string, string>
                            )[getPlayerStringValue(player, "status") ?? ""] ??
                              "common.unknown",
                          )}
                        </Badge>
                      </TableCell>
                    ) : null}
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
