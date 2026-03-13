import { useQuery } from "@tanstack/react-query"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { ArrowDown, ArrowUp, Grid, List, Search, Share2 } from "lucide-react"
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
import { CountryFlag } from "@/components/Common/CountryFlag"
import { PendingServers } from "@/components/Servers/PendingServers"
import { ServerCard } from "@/components/Servers/ServerCard"
import { ServerDetailSheet } from "@/components/Servers/ServerDetailSheet"
import { ServerTable } from "@/components/Servers/ServerTable"
import useCustomToast from "@/hooks/useCustomToast"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

import type {
  ServerRealtimeEvent,
  ServerSortKey,
  ServersSearchState,
} from "./utils"
import {
  buildServersWebSocketUrl,
  countOnlinePlayers,
  countOnlineServers,
  createServersSearchParams,
  getCountryCounts,
  getCountryPlayerCounts,
  getSelectedServerAddress,
  getServerAddress,
  matchesServerSearch,
  normalizeServersSearch,
  sortServers,
} from "./utils"

interface ServerBrowserProps {
  search: ServersSearchState
}

type ConnectionState = "connecting" | "live" | "disconnected"

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

export function ServerBrowser({ search }: ServerBrowserProps) {
  const navigate = useNavigate()
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const selectedAddress = getSelectedServerAddress(pathname)

  const [searchInput, setSearchInput] = useState(search.q)
  const deferredSearchInput = useDeferredValue(searchInput)
  const [servers, setServers] = useState<ServerPublic[]>([])
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("connecting")
  const seededRef = useRef(false)

  const serversQuery = useQuery({
    queryKey: ["servers", "seed"],
    queryFn: () => ServersService.readServers({ offset: 0, limit: 200 }),
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  useEffect(() => {
    setSearchInput(search.q)
  }, [search.q])

  useEffect(() => {
    if (!serversQuery.data || seededRef.current) {
      return
    }

    seededRef.current = true
    setServers(serversQuery.data.data)
  }, [serversQuery.data])

  const updateLocationSearch = useEffectEvent(
    (nextSearch: ServersSearchState) => {
      const normalizedSearch = normalizeServersSearch({ ...nextSearch })
      const nextPath = selectedAddress
        ? `/servers/${selectedAddress}`
        : "/servers"

      startTransition(() => {
        navigate({
          to: nextPath,
          search: normalizedSearch,
          replace: true,
        })
      })
    },
  )

  useEffect(() => {
    if (deferredSearchInput === search.q) {
      return
    }

    updateLocationSearch({ ...search, q: deferredSearchInput })
  }, [deferredSearchInput, search])

  const compactSearchString = useMemo(
    () => createServersSearchParams(search).toString(),
    [search],
  )

  useEffect(() => {
    const currentSearchString = window.location.search.startsWith("?")
      ? window.location.search.slice(1)
      : window.location.search
    const currentUrl = currentSearchString
      ? `${window.location.pathname}?${currentSearchString}`
      : window.location.pathname
    const nextUrl = compactSearchString
      ? `${pathname}?${compactSearchString}`
      : pathname

    if (currentUrl === nextUrl) {
      return
    }

    window.history.replaceState(window.history.state, "", nextUrl)
  }, [compactSearchString, pathname])

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
      if (search.status === "online" && !(server.status?.is_online ?? false)) {
        return false
      }

      if (
        search.country !== "all" &&
        server.country?.toUpperCase() !== search.country
      ) {
        return false
      }

      return matchesServerSearch(server, deferredSearchInput)
    })
  }, [deferredSearchInput, search.country, search.status, servers])

  const sortedServers = useMemo(
    () => sortServers(filteredServers, search.sort, search.dir),
    [filteredServers, search.dir, search.sort],
  )

  const countryOptions = useMemo(
    () => getCountryCounts(servers, search.status),
    [search.status, servers],
  )
  const countryPlayerCounts = useMemo(
    () => getCountryPlayerCounts(servers),
    [servers],
  )
  const onlinePlayerCount = useMemo(
    () => countOnlinePlayers(servers),
    [servers],
  )
  const onlineServerCount = useMemo(
    () => countOnlineServers(servers),
    [servers],
  )

  const handleSearchPatch = (patch: Partial<ServersSearchState>) => {
    updateLocationSearch({
      ...search,
      ...patch,
    })
  }

  const handleSelectServer = (server: ServerPublic) => {
    navigate({
      to: `/servers/${getServerAddress(server)}`,
      search,
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
      <div className="flex flex-col gap-6">
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
              {onlinePlayerCount} live players
            </Badge>
            <Badge variant="outline">{onlineServerCount} online servers</Badge>
            <Badge variant="secondary">{servers.length} total servers</Badge>
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

        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative w-full max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search IP, hostname, map, city, group..."
              className="pl-9"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant={search.status === "all" ? "default" : "outline"}
              className="h-10 gap-2 px-3"
              onClick={() =>
                handleSearchPatch({
                  status: search.status === "all" ? "online" : "all",
                })
              }
              aria-pressed={search.status === "all"}
              aria-label="Show offline servers"
            >
              <Checkbox
                checked={search.status === "all"}
                className="pointer-events-none"
                aria-hidden="true"
              />
              Show offline
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-10 gap-2 px-3"
              onClick={handleCopyShareLink}
              aria-label="Copy share link"
              title="Copy share link"
            >
              <Share2 className="h-4 w-4" />
              Share
            </Button>
          </div>
        </div>

        {countryOptions.length > 0 ? (
          <div className="rounded-md border px-6 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant={search.country === "all" ? "default" : "outline"}
                size="sm"
                onClick={() => handleSearchPatch({ country: "all" })}
              >
                <div className="flex items-center gap-2">
                  <span>All</span>
                  <span className="text-xs opacity-80">
                    ({onlinePlayerCount})
                  </span>
                </div>
              </Button>
              {countryOptions.map(([countryCode, count]) => (
                <Button
                  key={countryCode}
                  variant={
                    search.country === countryCode ? "default" : "outline"
                  }
                  size="sm"
                  onClick={() => handleSearchPatch({ country: countryCode })}
                >
                  <div className="flex items-center gap-2">
                    <CountryFlag
                      countryCode={countryCode}
                      showTooltip={false}
                    />
                    <span>{countryCode}</span>
                    <span className="text-xs opacity-80">
                      ({countryPlayerCounts.get(countryCode) ?? count})
                    </span>
                  </div>
                </Button>
              ))}
            </div>
          </div>
        ) : null}

        {sortedServers.length === 0 ? (
          <div className="py-12 text-center text-muted-foreground">
            No servers match the current filters.
          </div>
        ) : search.view === "table" ? (
          <ServerTable
            servers={sortedServers}
            selectedAddress={selectedAddress}
            sortKey={search.sort}
            sortDirection={search.dir}
            onSortChange={handleSortChange}
            onSelect={handleSelectServer}
            onCopyAddress={handleCopyAddress}
            onSteamConnect={handleSteamConnect}
          />
        ) : (
          <div className="space-y-4">
            <div className="rounded-md border bg-muted/20 px-6 py-3">
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
            search,
            replace: true,
          })
        }}
        onCopyAddress={handleCopyAddress}
        onSteamConnect={handleSteamConnect}
      />
    </>
  )
}
