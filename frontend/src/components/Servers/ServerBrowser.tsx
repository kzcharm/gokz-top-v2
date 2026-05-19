import { useQuery } from "@tanstack/react-query"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import {
  ArrowDown,
  ArrowUp,
  Download,
  Grid,
  List,
  Search,
  Share2,
} from "lucide-react"
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useMemo,
  useRef,
  useState,
} from "react"

import { type ServerPublic, ServersService } from "@/client"
import { RegionBadge } from "@/components/Common/RegionFlag"
import { AddServerButton } from "@/components/Servers/AddServerButton"
import { PendingServers } from "@/components/Servers/PendingServers"
import { ServerCard } from "@/components/Servers/ServerCard"
import { ServerDetailSheet } from "@/components/Servers/ServerDetailSheet"
import { ServerTable } from "@/components/Servers/ServerTable"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import useCustomToast from "@/hooks/useCustomToast"
import { getRegionsQueryOptions } from "@/lib/regions"
import { cn } from "@/lib/utils"

import type {
  ServerRealtimeEvent,
  ServerSortKey,
  ServersSearchState,
} from "./utils"
import {
  buildServerConfigFile,
  buildServersWebSocketUrl,
  countOnlinePlayers,
  countOnlineServers,
  createServersSearchParams,
  getRegionCounts,
  getSelectedServerAddress,
  getServerAddress,
  matchesServerSearch,
  matchesServerStatusFilter,
  normalizeServersSearch,
  SERVER_CONFIG_FILENAME,
  sortServers,
} from "./utils"

interface ServerBrowserProps {
  initialSearchString: string
}

type ConnectionState = "connecting" | "live" | "disconnected"

const SERVER_BROWSER_CARD_CLASS_NAME =
  "gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0"
const SERVER_BROWSER_CARD_CONTENT_CLASS_NAME = "p-6 sm:px-8 sm:pt-8 sm:pb-6"
const SERVER_BROWSER_HEADER_SURFACE_CLASS = "bg-muted"

function SortControl({
  active,
  direction,
  label,
  onClick,
}: {
  active: boolean
  direction: "asc" | "desc"
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className="flex items-center gap-2 rounded-md px-2 py-1 text-left hover:bg-accent -mx-2 -my-1"
      onClick={onClick}
    >
      <span className="text-sm font-medium">{label}</span>
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

export function ServerBrowser({ initialSearchString }: ServerBrowserProps) {
  const navigate = useNavigate()
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const selectedAddress = getSelectedServerAddress(pathname)
  const hydratedInitialSearch = useMemo(
    () =>
      normalizeServersSearch(
        Object.fromEntries(new URLSearchParams(initialSearchString)),
      ),
    [initialSearchString],
  )

  const [search, setSearch] = useState<ServersSearchState>(
    () => hydratedInitialSearch,
  )
  const [searchInput, setSearchInput] = useState(() => hydratedInitialSearch.q)
  const deferredSearchInput = useDeferredValue(searchInput)
  const [servers, setServers] = useState<ServerPublic[]>([])
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("connecting")
  const [configDialogOpen, setConfigDialogOpen] = useState(false)
  const seededRef = useRef(false)

  const serversQuery = useQuery({
    queryKey: ["servers", "seed"],
    queryFn: () => ServersService.readServers({ offset: 0, limit: 200 }),
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    retry: 1,
  })
  const regionsQuery = useQuery(getRegionsQueryOptions())

  useEffect(() => {
    startTransition(() => {
      setSearch(hydratedInitialSearch)
      setSearchInput(hydratedInitialSearch.q)
    })
  }, [hydratedInitialSearch])

  useEffect(() => {
    if (!serversQuery.data || seededRef.current) {
      return
    }

    seededRef.current = true
    setServers(serversQuery.data.data)
  }, [serversQuery.data])

  useEffect(() => {
    if (deferredSearchInput === search.q) {
      return
    }

    startTransition(() => {
      setSearch((currentSearch) =>
        normalizeServersSearch({
          ...currentSearch,
          q: deferredSearchInput,
        }),
      )
    })
  }, [deferredSearchInput, search.q])

  const handleRealtimeEvent = useEffectEvent((event: ServerRealtimeEvent) => {
    setServers((currentServers) => {
      if (event.type === "server.snapshot") {
        return event.servers
      }

      const nextServers = [...currentServers]
      const existingIndex = nextServers.findIndex(
        (server) => server.id === event.server.id,
      )

      if (existingIndex === -1) {
        nextServers.push(event.server)
        return nextServers
      }

      nextServers[existingIndex] = event.server
      return nextServers
    })
  })

  useEffect(() => {
    if (!serversQuery.data) {
      return
    }

    let websocket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0
    let shouldReconnect = true

    const connect = () => {
      setConnectionState((currentState) =>
        currentState === "live" ? currentState : "connecting",
      )

      websocket = new WebSocket(buildServersWebSocketUrl())

      websocket.onopen = () => {
        attempt = 0
        setConnectionState("live")
      }

      websocket.onmessage = (message) => {
        try {
          handleRealtimeEvent(JSON.parse(message.data) as ServerRealtimeEvent)
        } catch {
          setConnectionState("disconnected")
        }
      }

      websocket.onclose = () => {
        if (!shouldReconnect) {
          return
        }

        setConnectionState("disconnected")
        attempt += 1
        const delay = Math.min(1000 * 2 ** attempt, 15000)
        reconnectTimer = setTimeout(connect, delay)
      }

      websocket.onerror = () => {
        websocket?.close()
      }
    }

    connect()

    return () => {
      shouldReconnect = false
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      websocket?.close()
    }
  }, [serversQuery.data])

  const selectedServer = useMemo(
    () =>
      selectedAddress
        ? servers.find(
            (server) => getServerAddress(server) === selectedAddress,
          ) || null
        : null,
    [selectedAddress, servers],
  )

  const filteredServers = useMemo(() => {
    return servers.filter((server) => {
      if (!matchesServerStatusFilter(server, search.status)) {
        return false
      }

      if (
        search.region !== "all" &&
        server.region?.toUpperCase() !== search.region
      ) {
        return false
      }

      return matchesServerSearch(server, deferredSearchInput)
    })
  }, [deferredSearchInput, search.region, search.status, servers])

  const sortedServers = useMemo(
    () => sortServers(filteredServers, search.sort, search.dir),
    [filteredServers, search.dir, search.sort],
  )

  const regionOptions = useMemo(
    () => getRegionCounts(servers, search.status),
    [search.status, servers],
  )
  const totalOnlineServerCount = useMemo(
    () => countOnlineServers(servers),
    [servers],
  )
  const totalOfflineServerCount = servers.length - totalOnlineServerCount
  const filteredPlayerCount = useMemo(
    () => countOnlinePlayers(filteredServers),
    [filteredServers],
  )
  const filteredServerCount = filteredServers.length

  const handleSearchPatch = (patch: Partial<ServersSearchState>) => {
    startTransition(() => {
      setSearch((currentSearch) =>
        normalizeServersSearch({
          ...currentSearch,
          ...patch,
        }),
      )
    })
  }

  const handleSelectServer = (server: ServerPublic) => {
    navigate({
      to: `/servers/${getServerAddress(server)}`,
    })
  }

  const handleCopyAddress = async (server: ServerPublic) => {
    await navigator.clipboard.writeText(`connect ${getServerAddress(server)}`)
  }

  const handleSteamConnect = (server: ServerPublic) => {
    window.location.href = `steam://connect/${getServerAddress(server)}`
  }

  const handleSortChange = (nextSortKey: ServerSortKey) => {
    handleSearchPatch({
      sort: nextSortKey,
      dir:
        search.sort === nextSortKey
          ? search.dir === "asc"
            ? "desc"
            : "asc"
          : nextSortKey === "players"
            ? "desc"
            : "asc",
    })
  }

  const handleCopyShareLink = async () => {
    try {
      const shareUrl = new URL(window.location.origin)
      shareUrl.pathname = pathname
      shareUrl.search = createServersSearchParams(search, {
        includeDefaults: true,
      }).toString()

      await navigator.clipboard.writeText(shareUrl.toString())
      showSuccessToast("Copied the shareable servers link.")
    } catch {
      showErrorToast("Unable to copy the shareable servers link.")
    }
  }

  const handleDownloadConfig = () => {
    try {
      const blob = new Blob([buildServerConfigFile(sortedServers)], {
        type: "text/plain;charset=utf-8",
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = SERVER_CONFIG_FILENAME
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)

      showSuccessToast(
        `Downloaded config for ${sortedServers.length} visible server${sortedServers.length === 1 ? "" : "s"}.`,
      )
      setConfigDialogOpen(true)
    } catch {
      showErrorToast("Unable to download the server config right now.")
    }
  }

  const handleServerAdded = (server: ServerPublic) => {
    setServers((currentServers) => {
      const nextServers = [...currentServers]
      const existingIndex = nextServers.findIndex(
        (currentServer) => currentServer.id === server.id,
      )

      if (existingIndex === -1) {
        nextServers.push(server)
        return nextServers
      }

      nextServers[existingIndex] = server
      return nextServers
    })
  }

  if (serversQuery.isLoading && servers.length === 0) {
    return <PendingServers />
  }

  if (serversQuery.isError && servers.length === 0) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          Unable to load the public server browser right now. Try again later.
        </AlertDescription>
      </Alert>
    )
  }

  return (
    <>
      <div className="space-y-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Servers</h1>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Badge
              variant="outline"
              className={cn(
                connectionState === "live" &&
                  "border-green-500 text-green-600 dark:text-green-400",
                connectionState === "connecting" &&
                  "border-orange-500 text-orange-600 dark:text-orange-400",
                connectionState === "disconnected" &&
                  "border-gray-500 text-gray-500",
              )}
            >
              {connectionState === "live"
                ? "Live"
                : connectionState === "connecting"
                  ? "Reconnecting"
                  : "Disconnected"}
            </Badge>
            <Badge className="bg-orange-500 text-white">
              {filteredPlayerCount} Players
            </Badge>
            <Badge className="bg-blue-600 text-white hover:bg-blue-600/90">
              {filteredServerCount} Servers
            </Badge>
            <div className="flex gap-1">
              <Button
                variant={search.view === "table" ? "default" : "outline"}
                size="icon"
                onClick={() => handleSearchPatch({ view: "table" })}
                aria-label="Table view"
              >
                <List className="h-4 w-4" />
              </Button>
              <Button
                variant={search.view === "grid" ? "default" : "outline"}
                size="icon"
                onClick={() => handleSearchPatch({ view: "grid" })}
                aria-label="Grid view"
              >
                <Grid className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        <Card className={SERVER_BROWSER_CARD_CLASS_NAME}>
          <CardContent className={SERVER_BROWSER_CARD_CONTENT_CLASS_NAME}>
            <div className="flex flex-col gap-6">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="relative w-full max-w-sm">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={searchInput}
                    onChange={(event) => setSearchInput(event.target.value)}
                    placeholder="Search servers..."
                    className="pl-9"
                  />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className={cn(
                      "flex h-8 items-center gap-2 rounded-md border px-2.5 shadow-xs transition-colors outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      search.status === "online" &&
                        "border-green-600/30 bg-green-600/5",
                    )}
                    onClick={() =>
                      handleSearchPatch({
                        status:
                          search.status === "online" ? "offline" : "online",
                      })
                    }
                    title="Click to switch between online and offline servers"
                  >
                    <Switch
                      aria-hidden="true"
                      checked={search.status === "online"}
                      className="pointer-events-none"
                      tabIndex={-1}
                    />
                    <span
                      className={cn(
                        "text-xs font-medium",
                        search.status === "online" &&
                          "text-green-700 dark:text-green-400",
                      )}
                    >
                      Online
                    </span>
                  </button>
                  <AddServerButton onServerAdded={handleServerAdded} />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    onClick={handleDownloadConfig}
                    disabled={sortedServers.length === 0}
                    aria-label="Download server config"
                    title="Download server config"
                    data-testid="download-servers-config-button"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    onClick={handleCopyShareLink}
                    aria-label="Copy share link"
                    title="Copy share link"
                    data-testid="share-servers-button"
                  >
                    <Share2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              {regionOptions.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant={search.region === "all" ? "default" : "outline"}
                    size="sm"
                    onClick={() => handleSearchPatch({ region: "all" })}
                  >
                    <div className="flex items-center gap-2 whitespace-nowrap">
                      <span>All</span>
                      <span className="text-xs opacity-80">
                        (
                        {search.status === "online"
                          ? totalOnlineServerCount
                          : totalOfflineServerCount}
                        )
                      </span>
                    </div>
                  </Button>
                  {regionOptions.map(([regionCode, count]) => {
                    const region =
                      regionsQuery.data?.find(
                        (option) => option.code === regionCode,
                      ) ?? null
                    return (
                      <Button
                        key={regionCode}
                        variant={
                          search.region === regionCode ? "default" : "outline"
                        }
                        size="sm"
                        onClick={() =>
                          handleSearchPatch({ region: regionCode })
                        }
                      >
                        <div className="flex items-center gap-2 whitespace-nowrap">
                          <RegionBadge
                            regionCode={regionCode}
                            regionName={region?.name}
                          />
                          <span className="text-xs opacity-80">({count})</span>
                        </div>
                      </Button>
                    )
                  })}
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>

        {sortedServers.length === 0 ? (
          <Card className={SERVER_BROWSER_CARD_CLASS_NAME}>
            <CardContent className="px-6 py-16 text-center text-muted-foreground">
              No servers match the current filters.
            </CardContent>
          </Card>
        ) : search.view === "table" ? (
          <Card className={SERVER_BROWSER_CARD_CLASS_NAME}>
            <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
              <ServerTable
                servers={sortedServers}
                selectedAddress={selectedAddress}
                sortKey={search.sort}
                sortDirection={search.dir}
                onSortChange={handleSortChange}
                onSelect={handleSelectServer}
                onCopyAddress={handleCopyAddress}
                onSteamConnect={handleSteamConnect}
                headerSurfaceClassName={SERVER_BROWSER_HEADER_SURFACE_CLASS}
              />
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            <div
              className={cn(
                "rounded-[20px] border border-border/70 bg-muted/95 px-6 py-3 shadow-sm",
                SERVER_BROWSER_HEADER_SURFACE_CLASS,
              )}
            >
              <div className="flex flex-wrap gap-4">
                <SortControl
                  active={search.sort === "hostname"}
                  direction={search.dir}
                  label="Server"
                  onClick={() => handleSortChange("hostname")}
                />
                <SortControl
                  active={search.sort === "map"}
                  direction={search.dir}
                  label="Map"
                  onClick={() => handleSortChange("map")}
                />
                <SortControl
                  active={search.sort === "tier"}
                  direction={search.dir}
                  label="Tier"
                  onClick={() => handleSortChange("tier")}
                />
                <SortControl
                  active={search.sort === "players"}
                  direction={search.dir}
                  label="Players"
                  onClick={() => handleSortChange("players")}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-4">
              {sortedServers.map((server) => (
                <ServerCard
                  key={server.id}
                  server={server}
                  isSelected={selectedAddress === getServerAddress(server)}
                  onSelect={handleSelectServer}
                  onCopyAddress={handleCopyAddress}
                  onSteamConnect={handleSteamConnect}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <ServerDetailSheet
        open={selectedAddress !== null}
        serverAddress={selectedAddress}
        server={selectedServer}
        onOpenChange={(open) => {
          if (open) {
            return
          }

          navigate({
            to: "/servers",
            replace: true,
          })
        }}
        onCopyAddress={handleCopyAddress}
        onSteamConnect={handleSteamConnect}
      />
      <Dialog open={configDialogOpen} onOpenChange={setConfigDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Server config downloaded</DialogTitle>
            <DialogDescription>
              The file includes the servers currently visible in this browser,
              sorted by hostname.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p>
              Place <code>{SERVER_CONFIG_FILENAME}</code> in your game{" "}
              <code>cfg</code> folder.
            </p>
            <p>
              Run <code>exec {SERVER_CONFIG_FILENAME}</code> in the console, or
              add it to your <code>autoexec.cfg</code>.
            </p>
            <p>
              Executing the file prints the numbered hostnames to the console.
              Use <code>s1</code>, <code>s2</code>, <code>s3</code>, and so on
              to connect.
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
