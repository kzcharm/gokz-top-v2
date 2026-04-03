import { Copy, LoaderCircle, Play } from "lucide-react"

import type { ServerPublic } from "@/client"
import { CountryFlag } from "@/components/Common/CountryFlag"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
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
  getServerLocation,
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

function DetailCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/20 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 break-words text-sm font-medium">{value}</p>
    </div>
  )
}

export function ServerDetailSheet({
  open,
  serverAddress,
  server,
  onOpenChange,
  onCopyAddress,
  onSteamConnect,
}: ServerDetailSheetProps) {
  const { formatDateTime } = useDateTimeFormat()
  const mapName = server ? getServerMapName(server) : null
  const mapImageUrl = getServerMapImageUrl(mapName)
  const isRefreshing = server ? isServerStatusRefreshing(server) : false

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
                  {server.status?.max_players ?? 0}
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
                    aria-label="Refreshing server status"
                  >
                    <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                  </span>
                ) : null}
              </DialogTitle>
              <DialogDescription>
                {server.group?.name ? `${server.group.name} • ` : ""}
                {getServerAddress(server)}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6">
              {mapName ? (
                <div className="space-y-4">
                  <div className="flex justify-center">
                    <div className="relative aspect-video w-full max-w-xl overflow-hidden rounded-md bg-gray-100 dark:bg-gray-800">
                      {mapImageUrl ? (
                        <img
                          src={mapImageUrl}
                          alt={mapName}
                          className="h-full w-full object-cover"
                          loading="lazy"
                          decoding="async"
                          onError={(event) => {
                            event.currentTarget.style.display = "none"
                          }}
                        />
                      ) : null}
                    </div>
                  </div>
                  <div className="flex items-center justify-center gap-3">
                    <span className="text-lg font-semibold">{mapName}</span>
                    <TierBadge tier={server.map_tier} />
                  </div>
                </div>
              ) : null}

              <div className="grid gap-3 md:grid-cols-2">
                <DetailCard label="Endpoint" value={getServerAddress(server)} />
                <DetailCard
                  label="Last update"
                  value={formatDateTime(server.status?.updated_at, {
                    fallback: "Unknown",
                    display: "relative",
                  })}
                />
                <DetailCard
                  label="Group"
                  value={server.group?.name || "Unassigned"}
                />
                <DetailCard
                  label="Location"
                  value={getServerLocation(server) || "Unknown"}
                />
              </div>

              <div className="flex flex-wrap justify-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => onCopyAddress(server)}
                >
                  <Copy className="mr-2 h-4 w-4" />
                  Copy connect command
                </Button>
                <Button
                  type="button"
                  onClick={() => onSteamConnect(server)}
                  disabled={!isServerOnline(server)}
                >
                  <Play className="mr-2 h-4 w-4" />
                  Connect via Steam
                </Button>
              </div>

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
