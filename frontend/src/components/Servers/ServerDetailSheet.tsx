import { Copy, LoaderCircle, Play } from "lucide-react"

import type { ServerPublic } from "@/client"
import { CountryFlag } from "@/components/Common/CountryFlag"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { ServerPlayerList } from "@/components/Servers/ServerPlayerList"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

import {
  getOccupancyVariant,
  getServerAddress,
  getServerHostname,
  getServerLastSuccessfulQueryAt,
  getServerMapImageUrl,
  getServerMapName,
  getServerPlayerCount,
  getServerPlayers,
  isServerOnline,
  isServerStatusRefreshing,
} from "./utils"

interface ServerDetailSheetProps {
  open: boolean
  serverAddress: string | null
  server: ServerPublic | null
  onOpenChange: (open: boolean) => void
  onCopyAddress: (server: ServerPublic) => void
  onSteamConnect: (server: ServerPublic) => void
}

export function ServerDetailSheet({
  open,
  serverAddress,
  server,
  onOpenChange,
  onCopyAddress,
  onSteamConnect,
}: ServerDetailSheetProps) {
  const mapName = server ? getServerMapName(server) : null
  const mapImageUrl = getServerMapImageUrl(mapName)
  const isRefreshing = server ? isServerStatusRefreshing(server) : false
  const lastSuccessfulQueryAt = server
    ? getServerLastSuccessfulQueryAt(server)
    : null
  const subtitleParts = server
    ? [
        getServerAddress(server),
        server.group?.name || null,
        server.city || null,
      ].filter(Boolean)
    : []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[90vw] overflow-y-auto sm:max-w-5xl">
        {server ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex flex-wrap items-center gap-2">
                <CountryFlag countryCode={server.country} showTooltip={false} />
                <span>{getServerHostname(server)}</span>
                <Badge className={cn(getOccupancyVariant(server))}>
                  {getServerPlayerCount(server)}/
                  {server.live_status?.max_players ?? 0}
                </Badge>
                <Badge
                  className={cn(
                    isServerOnline(server)
                      ? "bg-green-500 text-white"
                      : "bg-gray-500 text-white",
                  )}
                >
                  {isServerOnline(server) ? "Online" : "Offline"}
                </Badge>
                {isRefreshing ? (
                  <span
                    className="inline-flex items-center text-muted-foreground"
                    title="Refreshing server status"
                  >
                    <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                  </span>
                ) : null}
              </DialogTitle>
              <DialogDescription className="flex flex-col gap-1 text-left sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                <span>{subtitleParts.join(" | ")}</span>
                {lastSuccessfulQueryAt ? (
                  <span className="shrink-0 text-xs">
                    Updated{" "}
                    <FormattedDateTime
                      value={lastSuccessfulQueryAt}
                      display="relative"
                    />
                  </span>
                ) : null}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6">
              {mapName ? (
                <div className="space-y-4">
                  <div className="flex justify-center">
                    <div className="group relative aspect-video w-full max-w-xl overflow-hidden rounded-xl bg-gray-100 dark:bg-gray-800">
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
                      <div className="absolute right-2 top-2 z-10 flex gap-1">
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          onClick={() => onCopyAddress(server)}
                          className="h-8 w-8 bg-transparent text-white hover:bg-white/10"
                          aria-label="Copy server address"
                          title="Copy server address"
                        >
                          <Copy className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          onClick={() => onSteamConnect(server)}
                          disabled={!isServerOnline(server)}
                          className="h-8 w-8 bg-transparent text-white hover:bg-white/10 disabled:opacity-40"
                          aria-label="Connect via Steam"
                          title="Connect via Steam"
                        >
                          <Play className="h-4 w-4" />
                        </Button>
                      </div>
                      <div className="absolute inset-x-2 top-2 flex items-center gap-1 pr-20">
                        <span
                          className="min-w-0 truncate rounded-md bg-black/45 px-2 py-1 text-sm font-semibold text-white"
                          title={mapName}
                        >
                          {mapName}
                        </span>
                        <TierBadge
                          tier={server.map_tier}
                          hideWhenUnknown
                          className="shrink-0 rounded-md px-2 py-1 text-xs font-bold"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}

              <ServerPlayerList players={getServerPlayers(server)} />
            </div>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Server not found</DialogTitle>
              <DialogDescription>
                No server snapshot is available for{" "}
                {serverAddress || "this route"}.
              </DialogDescription>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              The server may have gone offline or is not present in the latest
              cache.
            </p>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
