import { Pause } from "lucide-react"

import { CountryFlag } from "@/components/Common/CountryFlag"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
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
import { getInitials } from "@/utils"

import {
  formatTimerTime,
  getPlayerAvatarUrl,
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

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10" />
              <TableHead>Player</TableHead>
              <TableHead>Timer</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Progress</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedPlayers.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={6}
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
                const country = getPlayerStringValue(player, "country")
                const mode = getPlayerStringValue(player, "mode")
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
                      <div className="flex justify-center">
                        <CountryFlag
                          countryCode={country}
                          showTooltip={false}
                          fallbackClassName="h-4 w-4 rounded-full"
                        />
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Avatar className="h-6 w-6">
                          <AvatarImage
                            src={getPlayerAvatarUrl(player) || undefined}
                            alt={name}
                          />
                          <AvatarFallback className="bg-zinc-600 text-[10px] text-white">
                            {getInitials(name)}
                          </AvatarFallback>
                        </Avatar>
                        <span className="truncate">
                          {mode ? `[${mode}] ` : ""}
                          {name}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {formatTimerTime(timerTime)}
                      {isPaused ? (
                        <Pause className="ml-1 inline h-3 w-3 align-middle text-muted-foreground" />
                      ) : null}
                    </TableCell>
                    <TableCell>{formatTimerTime(durationSeconds)}</TableCell>
                    <TableCell>
                      {progress !== null ? (
                        <div className="flex min-w-[9rem] items-center gap-2">
                          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${progress}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {progress.toFixed(1)}%
                          </span>
                        </div>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge className={cn(badgeClassName)}>
                        {getPlayerStatusLabel(player)}
                      </Badge>
                    </TableCell>
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
