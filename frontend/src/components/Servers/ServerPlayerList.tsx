import { Pause } from "lucide-react"

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
import { cn } from "@/lib/utils"

import {
  formatTimerTime,
  getPlayerBooleanValue,
  getPlayerNumberValue,
  getPlayerProgressPercent,
  getPlayerStatusLabel,
  getPlayerStatusSurfaceClass,
  getPlayerStringValue,
  type ServerPlayer,
  sortPlayersByProgress,
} from "./utils"

export function ServerPlayerList({ players }: { players: ServerPlayer[] }) {
  const sortedPlayers = sortPlayersByProgress(players)
  const showTimerColumn = sortedPlayers.some(
    (player) => getPlayerNumberValue(player, "timer_time") !== null,
  )
  const showProgressColumn = sortedPlayers.some(
    (player) => getPlayerProgressPercent(player) !== null,
  )
  const showStatusColumn = sortedPlayers.some(
    (player) => getPlayerStringValue(player, "status") !== null,
  )
  const visibleColumnCount =
    2 +
    (showTimerColumn ? 1 : 0) +
    (showProgressColumn ? 1 : 0) +
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
              <TableHead>Player</TableHead>
              {showTimerColumn ? <TableHead>Timer</TableHead> : null}
              <TableHead>Duration</TableHead>
              {showProgressColumn ? <TableHead>Progress</TableHead> : null}
              {showStatusColumn ? <TableHead>Status</TableHead> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedPlayers.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={visibleColumnCount}
                  className="h-24 text-center text-muted-foreground"
                >
                  No live players on this server.
                </TableCell>
              </TableRow>
            ) : (
              sortedPlayers.map((player, index) => {
                const name =
                  getPlayerStringValue(player, "name") || `Player ${index + 1}`
                const steamid64 = getPlayerStringValue(player, "steamid64")
                const timerTime = getPlayerNumberValue(player, "timer_time")
                const durationSeconds = getPlayerNumberValue(
                  player,
                  "duration_seconds",
                )
                const progress = getPlayerProgressPercent(player)
                const isPaused = getPlayerBooleanValue(player, "is_paused")
                const { badgeClassName } = getPlayerStatusSurfaceClass(player)
                const rowKey = steamid64 || `${name}-${index}`

                return (
                  <TableRow key={rowKey}>
                    <TableCell>
                      <PlayerDisplay
                        player={{
                          steamid64: steamid64 || "",
                          name,
                          avatar_hash: getPlayerStringValue(player, "avatar_hash"),
                          country: getPlayerStringValue(player, "country"),
                        }}
                        fallbackSteamid64={steamid64 || undefined}
                        className="max-w-[18rem]"
                        nameMaxLength={28}
                        disableProfileLink={!steamid64}
                      />
                    </TableCell>
                    {showTimerColumn ? (
                      <TableCell>
                        {formatTimerTime(timerTime)}
                        {isPaused ? (
                          <Pause className="ml-1 inline h-3 w-3 align-middle text-muted-foreground" />
                        ) : null}
                      </TableCell>
                    ) : null}
                    <TableCell>{formatTimerTime(durationSeconds)}</TableCell>
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
                          {getPlayerStatusLabel(player)}
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
