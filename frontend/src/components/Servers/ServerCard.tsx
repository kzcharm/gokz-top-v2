import { Copy, LoaderCircle, Pause, Play } from "lucide-react"
import { memo, useMemo } from "react"

import type { ServerPublic } from "@/client"
import { CountryFlag } from "@/components/Common/CountryFlag"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { getInitials } from "@/utils"

import {
  formatTimerTime,
  getPlayerAvatarUrl,
  getPlayerBooleanValue,
  getPlayerNumberValue,
  getPlayerProgressPercent,
  getPlayerStatusSurfaceClass,
  getPlayerStringValue,
  getServerHostname,
  getServerMapImageUrl,
  getServerMapName,
  getServerPlayerCount,
  getServerPlayers,
  getServerSurfaceClass,
  isServerOnline,
  isServerStatusRefreshing,
  sortPlayersByProgress,
} from "./utils"

interface ServerCardProps {
  server: ServerPublic
  isSelected: boolean
  onSelect: (server: ServerPublic) => void
  onCopyAddress: (server: ServerPublic) => void
  onSteamConnect: (server: ServerPublic) => void
}

export const ServerCard = memo(function ServerCard({
  server,
  isSelected,
  onSelect,
  onCopyAddress,
  onSteamConnect,
}: ServerCardProps) {
  const mapName = getServerMapName(server)
  const mapImageUrl = useMemo(() => getServerMapImageUrl(mapName), [mapName])
  const playerCount = getServerPlayerCount(server)
  const maxPlayers = server.live_status?.max_players ?? 0
  const isFull = maxPlayers > 0 && playerCount >= maxPlayers
  const isEmpty = playerCount === 0
  const offline = !isServerOnline(server)
  const isRefreshing = isServerStatusRefreshing(server)
  const sortedPlayers = useMemo(
    () => sortPlayersByProgress(getServerPlayers(server)),
    [server],
  )

  return (
    <div
      data-testid={`server-card-${server.ip}:${server.port}`}
      className={cn(
        "group relative isolate overflow-hidden rounded-md border bg-white transition-all duration-200 dark:bg-gray-800",
        offline && "opacity-60",
        getServerSurfaceClass(isSelected),
      )}
    >
      <div className="absolute right-2 top-2 z-10 flex gap-1">
        <Button
          size="icon"
          variant="ghost"
          onClick={(event) => {
            event.stopPropagation()
            onCopyAddress(server)
          }}
          className="h-6 w-6 bg-transparent text-white hover:bg-white/10"
          aria-label="Copy server address"
          title="Copy server address"
        >
          <Copy className="h-3 w-3" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          onClick={(event) => {
            event.stopPropagation()
            onSteamConnect(server)
          }}
          disabled={offline}
          className="h-6 w-6 bg-transparent text-white hover:bg-white/10 disabled:opacity-40"
          aria-label="Connect via Steam"
          title="Connect via Steam"
        >
          <Play className="h-3 w-3" />
        </Button>
      </div>

      <button
        type="button"
        className="block w-full text-left"
        onClick={() => onSelect(server)}
      >
        <div className="relative aspect-video w-full overflow-hidden bg-gray-100 dark:bg-gray-800">
          {mapImageUrl ? (
            <div
              className="absolute inset-0 bg-cover bg-center transition-transform duration-300 group-hover:scale-105"
              style={{ backgroundImage: `url(${mapImageUrl})` }}
            />
          ) : null}
          <div
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(to bottom, rgba(0,0,0,0.65) 0%, rgba(0,0,0,0.0) 40%, rgba(0,0,0,0.65) 100%)",
            }}
          />

          <div className="absolute inset-x-2 top-2 flex items-center gap-1">
            <div className="flex min-w-0 flex-1 items-center gap-1">
              <span
                className="min-w-0 truncate rounded-md bg-black/45 px-2 py-1 text-sm font-semibold text-white"
                title={mapName || "-"}
              >
                {mapName || "-"}
              </span>
              <TierBadge
                tier={server.map_tier}
                hideWhenUnknown
                className="shrink-0 rounded-md px-2 py-1 text-xs font-bold"
              />
            </div>
            <div className="h-6 w-14 shrink-0" />
          </div>
        </div>

        <div className="relative z-10 bg-white p-3 dark:bg-gray-800">
          <div className="flex items-center gap-2">
            <CountryFlag countryCode={server.country} showTooltip={false} />
            <span
              className="truncate font-semibold"
              title={getServerHostname(server)}
            >
              {getServerHostname(server)}
            </span>
            {isRefreshing ? (
              <span
                className="inline-flex shrink-0 items-center text-muted-foreground"
                title="Refreshing server status"
              >
                <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
              </span>
            ) : null}
            <Badge
              className={cn(
                "ml-auto shrink-0",
                offline
                  ? "bg-gray-500 text-white"
                  : isFull
                    ? "bg-red-500 text-white"
                    : isEmpty
                      ? "bg-green-500 text-white"
                      : "bg-orange-500 text-white",
              )}
            >
              {playerCount}/{maxPlayers}
            </Badge>
          </div>

          {sortedPlayers.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-2">
              {sortedPlayers.map((player, index) => {
                const name =
                  getPlayerStringValue(player, "name") || `Player ${index + 1}`
                const steamid64 = getPlayerStringValue(player, "steamid64")
                const mode = getPlayerStringValue(player, "mode")
                const progress = getPlayerProgressPercent(player)
                const isPaused = getPlayerBooleanValue(player, "is_paused")
                const timerLabel = formatTimerTime(
                  getPlayerNumberValue(player, "timer_time"),
                )
                const avatarUrl = getPlayerAvatarUrl(player)
                const { backgroundClassName } =
                  getPlayerStatusSurfaceClass(player)

                return (
                  <div
                    key={`${name}-${index}`}
                    className={cn(
                      "relative flex min-w-0 items-center gap-2 rounded-md px-2 py-1 text-xs",
                      backgroundClassName,
                    )}
                  >
                    {progress !== null ? (
                      <div
                        className="absolute inset-y-0 left-0 rounded-md bg-blue-500/15 dark:bg-blue-400/15"
                        style={{ width: `${progress}%` }}
                      />
                    ) : null}
                    {steamid64 ? (
                      <Avatar className="relative z-10 h-4 w-4">
                        <AvatarImage src={avatarUrl || undefined} alt={name} />
                        <AvatarFallback className="bg-zinc-600 text-[9px] text-white">
                          {getInitials(name)}
                        </AvatarFallback>
                      </Avatar>
                    ) : null}
                    <span className="relative z-10 min-w-0 truncate">
                      {mode ? (
                        <span className="mr-1 text-gray-500">[{mode}]</span>
                      ) : null}
                      {name}
                      {timerLabel !== "-" ? (
                        <span className="ml-1 text-gray-500">
                          - {timerLabel}
                          {isPaused ? (
                            <Pause className="ml-1 inline h-3 w-3 align-middle" />
                          ) : null}
                        </span>
                      ) : null}
                    </span>
                  </div>
                )
              })}
            </div>
          ) : null}
        </div>
      </button>
    </div>
  )
})
