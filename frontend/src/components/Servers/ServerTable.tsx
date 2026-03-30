import { ArrowDown, ArrowUp, Copy, LoaderCircle, Play } from "lucide-react"

import type { ServerPublic } from "@/client"
import { CountryFlag } from "@/components/Common/CountryFlag"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"

import type { ServerSortDirection, ServerSortKey } from "./utils"
import {
  getOccupancyVariant,
  getServerAddress,
  getServerHostname,
  getServerMapName,
  isServerOnline,
  isServerStatusRefreshing,
} from "./utils"

interface ServerTableProps {
  servers: ServerPublic[]
  selectedAddress: string | null
  sortKey: ServerSortKey
  sortDirection: ServerSortDirection
  onSortChange: (sortKey: ServerSortKey) => void
  onSelect: (server: ServerPublic) => void
  onCopyAddress: (server: ServerPublic) => void
  onSteamConnect: (server: ServerPublic) => void
}

function SortButton({
  active,
  direction,
  label,
  onClick,
}: {
  active: boolean
  direction: ServerSortDirection
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className="flex items-center gap-2 rounded-md px-2 py-1 text-left text-sm font-medium hover:bg-accent -mx-2 -my-1"
      onClick={onClick}
    >
      <span>{label}</span>
      {active ? (
        direction === "asc" ? (
          <ArrowUp className="h-3 w-3" />
        ) : (
          <ArrowDown className="h-3 w-3" />
        )
      ) : null}
    </button>
  )
}

export function ServerTable({
  servers,
  selectedAddress,
  sortKey,
  sortDirection,
  onSortChange,
  onSelect,
  onCopyAddress,
  onSteamConnect,
}: ServerTableProps) {
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-12">
              <span className="sr-only">Country</span>
            </TableHead>
            <TableHead className="w-[28%]">
              <SortButton
                active={sortKey === "hostname"}
                direction={sortDirection}
                label="Server"
                onClick={() => onSortChange("hostname")}
              />
            </TableHead>
            <TableHead className="w-[24%]">
              <SortButton
                active={sortKey === "map"}
                direction={sortDirection}
                label="Map"
                onClick={() => onSortChange("map")}
              />
            </TableHead>
            <TableHead className="w-[12%]">
              <SortButton
                active={sortKey === "tier"}
                direction={sortDirection}
                label="Tier"
                onClick={() => onSortChange("tier")}
              />
            </TableHead>
            <TableHead className="w-[12%]">
              <SortButton
                active={sortKey === "players"}
                direction={sortDirection}
                label="Players"
                onClick={() => onSortChange("players")}
              />
            </TableHead>
            <TableHead className="w-[12%] text-right">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {servers.length > 0 ? (
            servers.map((server) => {
              const address = getServerAddress(server)
              const mapName = getServerMapName(server)
              const isSelected = selectedAddress === address
              const isRefreshing = isServerStatusRefreshing(server)

              return (
                <TableRow
                  key={address}
                  data-testid={`server-row-${address}`}
                  className={cn(
                    "cursor-pointer transition-[background-color,box-shadow] hover:bg-muted/50",
                    !isServerOnline(server) && "opacity-60",
                    isSelected &&
                      "bg-muted/50 shadow-[inset_0_0_0_1px_var(--color-primary)] [animation:server-selected_650ms_ease-out]",
                  )}
                  onClick={() => onSelect(server)}
                >
                  <TableCell>
                    <div className="flex justify-center">
                      <CountryFlag
                        countryCode={server.country}
                        showTooltip={false}
                      />
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        {!isServerOnline(server) ? (
                          <div
                            className="h-2 w-2 rounded-full bg-gray-400"
                            title="Offline"
                          />
                        ) : null}
                        <span
                          className={cn(
                            "font-medium",
                            !isServerOnline(server) && "text-muted-foreground",
                          )}
                        >
                          {getServerHostname(server)}
                        </span>
                        {isRefreshing ? (
                          <span
                            className="inline-flex items-center text-muted-foreground"
                            title="Refreshing server status"
                            aria-label="Refreshing server status"
                          >
                            <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                          </span>
                        ) : null}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        <span className="font-mono">{address}</span>
                        {server.group?.name ? (
                          <>
                            <span className="mx-1">•</span>
                            <span>{server.group.name}</span>
                          </>
                        ) : null}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <MapDisplay mapName={mapName} />
                  </TableCell>
                  <TableCell>
                    {server.map_tier === null ||
                    server.map_tier === undefined ? (
                      <span className="text-muted-foreground">-</span>
                    ) : (
                      <TierBadge tier={server.map_tier} hideWhenUnknown />
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge className={cn(getOccupancyVariant(server))}>
                      {server.status?.player_count ?? 0}/
                      {server.status?.max_players ?? 0}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={(event) => {
                          event.stopPropagation()
                          onCopyAddress(server)
                        }}
                        title="Copy server address"
                        aria-label="Copy server address"
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={(event) => {
                          event.stopPropagation()
                          onSteamConnect(server)
                        }}
                        disabled={!isServerOnline(server)}
                        title="Connect via Steam"
                        aria-label="Connect via Steam"
                      >
                        <Play className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })
          ) : (
            <TableRow>
              <TableCell
                colSpan={6}
                className="h-32 text-center text-muted-foreground"
              >
                No servers match the current filters.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
