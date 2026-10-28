import { useQuery } from "@tanstack/react-query"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import {
  ArrowDown,
  ArrowUp,
  Download,
  Grid,
  List,
  Map as MapIcon,
  Search,
  Share2,
} from "lucide-react"
import {
  startTransition,
  useCallback,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useMemo,
  useRef,
  useState,
} from "react"
import { Trans, useTranslation } from "react-i18next"

import { MapsService, type ServerPublic, ServersService } from "@/client"
import { CountryFlag } from "@/components/Common/CountryFlag"
import { RegionBadge } from "@/components/Common/RegionFlag"
import { AddServerButton } from "@/components/Servers/AddServerButton"
import { PendingServers } from "@/components/Servers/PendingServers"
import { ServerCard } from "@/components/Servers/ServerCard"
import { ServerDetailSheet } from "@/components/Servers/ServerDetailSheet"
import { ServerTable } from "@/components/Servers/ServerTable"
import { ServerWorldMapDialog } from "@/components/Servers/ServerWorldMapDialog"
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
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import useCustomToast from "@/hooks/useCustomToast"
import { getMapDownloadUrl } from "@/lib/map-downloads"
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
  canSteamConnect,
  countOnlinePlayers,
  createServersSearchParams,
  getRegionCounts,
  getSelectedServerAddress,
  getSelectedServerGroupCustomId,
  getServerAddress,
  getServerBrowserRegion,
  getServerGroupCounts,
  getServerMapName,
  getServerPlayerCount,
  matchesServerGroupFilter,
  matchesServerSearch,
  matchesServerStatusFilter,
  normalizeServersSearch,
  readServersFilterPreferences,
  SERVER_CONFIG_FILENAME,
  sortServers,
  UNASSIGNED_SERVER_GROUP_CUSTOM_ID,
  UNASSIGNED_SERVER_GROUP_ID,
  writeServersFilterPreferences,
} from "./utils"

interface ServerBrowserProps {
  initialSearchString: string
}

type ConnectionState = "connecting" | "live" | "disconnected"

const SERVER_BROWSER_CARD_CLASS_NAME =
  "gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0"
const SERVER_BROWSER_HEADER_SURFACE_CLASS = "bg-muted"

const scrollToServerBrowserTop = () => {
  window.scrollTo({ top: 0, left: 0 })
}

const playCopySuccessSound = () => {
  const AudioContextConstructor =
    window.AudioContext ||
    (
      window as Window &
        typeof globalThis & {
          webkitAudioContext?: typeof AudioContext
        }
    ).webkitAudioContext

  if (!AudioContextConstructor) {
    return
  }

  try {
    const audioContext = new AudioContextConstructor()
    const masterGain = audioContext.createGain()
    masterGain.gain.setValueAtTime(0.18, audioContext.currentTime)
    masterGain.connect(audioContext.destination)

    const notes = [
      { frequency: 523.25, start: 0, duration: 0.09 },
      { frequency: 659.25, start: 0.08, duration: 0.1 },
      { frequency: 783.99, start: 0.17, duration: 0.16 },
    ]

    for (const note of notes) {
      const oscillator = audioContext.createOscillator()
      const gain = audioContext.createGain()
      const startsAt = audioContext.currentTime + note.start
      const endsAt = startsAt + note.duration

      oscillator.type = "triangle"
      oscillator.frequency.setValueAtTime(note.frequency, startsAt)
      gain.gain.setValueAtTime(0.001, startsAt)
      gain.gain.exponentialRampToValueAtTime(0.7, startsAt + 0.015)
      gain.gain.exponentialRampToValueAtTime(0.001, endsAt)

      oscillator.connect(gain)
      gain.connect(masterGain)
      oscillator.start(startsAt)
      oscillator.stop(endsAt)
    }

    window.setTimeout(() => {
      void audioContext.close()
    }, 500)
  } catch {
    // Copy feedback should never make the copy action fail.
  }
}

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
  const { t } = useTranslation()
  const navigate = useNavigate()
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [, copyToClipboard] = useCopyToClipboard()
  const selectedAddress = getSelectedServerAddress(pathname)
  const selectedGroupCustomId = getSelectedServerGroupCustomId(pathname)
  const hydratedInitialSearch = useMemo(() => {
    const searchParams = new URLSearchParams(initialSearchString)
    const urlSearch = Object.fromEntries(searchParams)
    const savedFilters = readServersFilterPreferences()
    const searchWithSavedFilters = {
      ...urlSearch,
      group: searchParams.has("group")
        ? urlSearch.group
        : (savedFilters?.group ?? urlSearch.group),
      region: searchParams.has("region")
        ? urlSearch.region
        : (savedFilters?.region ?? urlSearch.region),
      sort: searchParams.has("sort")
        ? urlSearch.sort
        : (savedFilters?.sort ?? urlSearch.sort),
      dir: searchParams.has("dir")
        ? urlSearch.dir
        : (savedFilters?.dir ?? urlSearch.dir),
    }

    return normalizeServersSearch(searchWithSavedFilters)
  }, [initialSearchString])

  const [search, setSearch] = useState<ServersSearchState>(
    () => hydratedInitialSearch,
  )
  const [searchInput, setSearchInput] = useState(() => hydratedInitialSearch.q)
  const deferredSearchInput = useDeferredValue(searchInput)
  const [servers, setServers] = useState<ServerPublic[]>([])
  const [serversSeeded, setServersSeeded] = useState(false)
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("connecting")
  const [configDialogOpen, setConfigDialogOpen] = useState(false)
  const [mapDialogOpen, setMapDialogOpen] = useState(false)
  const seededRef = useRef(false)

  const serversQuery = useQuery({
    queryKey: ["servers", "seed"],
    queryFn: () => ServersService.readServers({ offset: 0, limit: 200 }),
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    retry: 1,
  })
  const mapsQuery = useQuery({
    queryKey: ["servers", "map-downloads"],
    queryFn: () =>
      MapsService.readMaps({ offset: 0, limit: 10000, isValidated: true }),
    staleTime: 1000 * 60 * 5,
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
    setServersSeeded(true)
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

      if (event.type === "server.removed") {
        return currentServers.filter((server) => server.id !== event.server_id)
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

  const selectedGroupId = useMemo(() => {
    if (!selectedGroupCustomId) {
      return null
    }

    const serverGroupId = servers.find(
      (server) => server.group?.custom_id === selectedGroupCustomId,
    )?.group_id
    if (serverGroupId) {
      return serverGroupId
    }

    return selectedGroupCustomId === UNASSIGNED_SERVER_GROUP_CUSTOM_ID
      ? UNASSIGNED_SERVER_GROUP_ID
      : null
  }, [selectedGroupCustomId, servers])

  const activeSearch = useMemo(
    () =>
      selectedGroupId
        ? {
            ...search,
            group: selectedGroupId,
          }
        : search,
    [search, selectedGroupId],
  )

  const filteredServers = useMemo(() => {
    return servers.filter((server) => {
      if (!matchesServerStatusFilter(server, activeSearch.status)) {
        return false
      }

      const playerCount = getServerPlayerCount(server)
      if (
        (activeSearch.hide_empty && playerCount === 0) ||
        (activeSearch.hide_occupied && playerCount > 0)
      ) {
        return false
      }

      if (!matchesServerGroupFilter(server, activeSearch.group)) {
        return false
      }

      if (
        activeSearch.region !== "all" &&
        getServerBrowserRegion(server) !== activeSearch.region
      ) {
        return false
      }

      return matchesServerSearch(server, deferredSearchInput)
    })
  }, [
    activeSearch.group,
    activeSearch.hide_empty,
    activeSearch.hide_occupied,
    activeSearch.region,
    activeSearch.status,
    deferredSearchInput,
    servers,
  ])

  const sortedServers = useMemo(
    () => sortServers(filteredServers, activeSearch.sort, activeSearch.dir),
    [activeSearch.dir, activeSearch.sort, filteredServers],
  )

  const groupOptions = useMemo(
    () => getServerGroupCounts(servers, activeSearch.status),
    [activeSearch.status, servers],
  )
  const selectedGroupReturnPath = useMemo(() => {
    const groupId = selectedGroupId ?? search.group
    if (groupId === "all") {
      return null
    }

    const customId = groupOptions.find(([id]) => id === groupId)?.[1].customId
    return customId ? `/servers/group/${customId}` : null
  }, [groupOptions, search.group, selectedGroupId])
  const regionSourceServers = useMemo(
    () =>
      servers.filter((server) =>
        matchesServerGroupFilter(server, activeSearch.group),
      ),
    [activeSearch.group, servers],
  )
  const regionOptions = useMemo(
    () => getRegionCounts(regionSourceServers, activeSearch.status),
    [activeSearch.status, regionSourceServers],
  )
  const mapDownloadUrls = useMemo(() => {
    const entries =
      mapsQuery.data
        ?.map((map) => {
          const downloadUrl = getMapDownloadUrl(map)
          return downloadUrl
            ? ([map.name.toLowerCase(), downloadUrl] as const)
            : null
        })
        .filter(
          (entry): entry is readonly [string, string] => entry !== null,
        ) ?? []

    return new Map(entries)
  }, [mapsQuery.data])
  const filteredPlayerCount = useMemo(
    () => countOnlinePlayers(filteredServers),
    [filteredServers],
  )
  const filteredServerCount = filteredServers.length

  const handleSearchPatch = useCallback(
    (patch: Partial<ServersSearchState>) => {
      startTransition(() => {
        setSearch((currentSearch) =>
          normalizeServersSearch({
            ...currentSearch,
            ...patch,
          }),
        )
      })
    },
    [],
  )

  useEffect(() => {
    writeServersFilterPreferences({
      group: activeSearch.group,
      region: activeSearch.region,
      sort: activeSearch.sort,
      dir: activeSearch.dir,
    })
  }, [
    activeSearch.dir,
    activeSearch.group,
    activeSearch.region,
    activeSearch.sort,
  ])

  useEffect(() => {
    if (!serversSeeded) {
      return
    }

    const nextPatch: Partial<ServersSearchState> = {}
    const nextGroup =
      activeSearch.group !== "all" &&
      !groupOptions.some(([groupId]) => groupId === activeSearch.group)
        ? "all"
        : activeSearch.group

    const regionIsAvailable =
      nextGroup === activeSearch.group
        ? regionOptions.some(
            ([regionCode]) => regionCode === activeSearch.region,
          )
        : servers.some(
            (server) =>
              matchesServerStatusFilter(server, activeSearch.status) &&
              matchesServerGroupFilter(server, nextGroup) &&
              getServerBrowserRegion(server) === activeSearch.region,
          )

    if (activeSearch.group !== "all" && nextGroup !== activeSearch.group) {
      nextPatch.group = nextGroup
    }

    if (activeSearch.region !== "all" && !regionIsAvailable) {
      nextPatch.region = "all"
    }

    if (nextPatch.group || nextPatch.region) {
      handleSearchPatch(nextPatch)
    }
  }, [
    serversSeeded,
    groupOptions,
    regionOptions,
    servers,
    activeSearch.group,
    activeSearch.region,
    activeSearch.status,
    handleSearchPatch,
  ])

  const handleSelectServer = (server: ServerPublic) => {
    navigate({
      to: `/servers/${getServerAddress(server)}`,
    })
  }

  const handleCopyAddress = async (server: ServerPublic) => {
    const copied = await copyToClipboard(`connect ${getServerAddress(server)}`)

    if (copied) {
      playCopySuccessSound()
      showSuccessToast(t("serverBrowser.copiedCommand"))
      return
    }

    showErrorToast(t("serverBrowser.copyCommandFailed"))
  }

  const handleSteamConnect = (server: ServerPublic) => {
    if (!canSteamConnect(server)) return
    window.location.href = `steam://connect/${getServerAddress(server)}`
  }

  const handleSortChange = (nextSortKey: ServerSortKey) => {
    handleSearchPatch({
      sort: nextSortKey,
      dir:
        activeSearch.sort === nextSortKey
          ? activeSearch.dir === "asc"
            ? "desc"
            : "asc"
          : nextSortKey === "players"
            ? "desc"
            : "asc",
    })
  }

  const handleGroupChange = (groupId: string) => {
    const nextGroup = activeSearch.group === groupId ? "all" : groupId
    const nextPatch: Partial<ServersSearchState> = { group: nextGroup }

    if (activeSearch.region !== "all" && nextGroup !== "all") {
      const groupHasSelectedRegion = servers.some(
        (server) =>
          matchesServerStatusFilter(server, activeSearch.status) &&
          matchesServerGroupFilter(server, nextGroup) &&
          getServerBrowserRegion(server) === activeSearch.region,
      )

      if (!groupHasSelectedRegion) {
        nextPatch.region = "all"
      }
    }

    handleSearchPatch(nextPatch)
    scrollToServerBrowserTop()

    if (nextGroup === "all") {
      navigate({ to: "/servers" })
      return
    }

    const customId = groupOptions.find(([id]) => id === nextGroup)?.[1].customId
    if (customId) {
      navigate({ to: `/servers/group/${customId}` })
    }
  }

  const handleRegionChange = (regionCode: string) => {
    handleSearchPatch({
      region: activeSearch.region === regionCode ? "all" : regionCode,
    })
  }

  const handleCopyShareLink = async () => {
    try {
      const shareUrl = new URL(window.location.origin)
      shareUrl.pathname = pathname
      shareUrl.search = createServersSearchParams(activeSearch, {
        includeDefaults: true,
      }).toString()

      const copied = await copyToClipboard(shareUrl.toString())

      if (!copied) {
        throw new Error("Copy failed")
      }

      playCopySuccessSound()
      showSuccessToast(t("serverBrowser.copiedLink"))
    } catch {
      showErrorToast(t("serverBrowser.copyLinkFailed"))
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
        t("serverBrowser.downloaded", { count: sortedServers.length }),
      )
      setConfigDialogOpen(true)
    } catch {
      showErrorToast(t("serverBrowser.downloadFailed"))
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
        <AlertDescription>{t("serverBrowser.loadFailed")}</AlertDescription>
      </Alert>
    )
  }

  return (
    <>
      <div className="space-y-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder={t("serverBrowser.searchPlaceholder")}
              aria-label={t("serverBrowser.search")}
              className="h-9 bg-[#f5f5f4] pl-8 text-sm dark:bg-input/30"
            />
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
                ? t("serverBrowser.live")
                : connectionState === "connecting"
                  ? t("serverBrowser.connecting")
                  : t("serverBrowser.disconnected")}
            </Badge>
            <Badge className="bg-orange-500 text-white">
              {t("serverBrowser.playersCount", { count: filteredPlayerCount })}
            </Badge>
            <Badge className="bg-blue-600 text-white hover:bg-blue-600/90">
              {t("serverBrowser.serversCount", { count: filteredServerCount })}
            </Badge>
            <div className="flex gap-1">
              <Button
                variant={activeSearch.view === "table" ? "default" : "outline"}
                size="icon"
                onClick={() => handleSearchPatch({ view: "table" })}
                aria-label={t("serverBrowser.tableView")}
              >
                <List className="h-4 w-4" />
              </Button>
              <Button
                variant={activeSearch.view === "grid" ? "default" : "outline"}
                size="icon"
                onClick={() => handleSearchPatch({ view: "grid" })}
                aria-label={t("serverBrowser.gridView")}
              >
                <Grid className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        <Card className={SERVER_BROWSER_CARD_CLASS_NAME}>
          <CardContent className="p-4 sm:px-6 sm:py-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex min-w-0 flex-1 flex-col gap-4">
                {groupOptions.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-2">
                    {groupOptions.map(([groupId, group]) => (
                      <Button
                        key={groupId}
                        type="button"
                        variant={
                          activeSearch.group === groupId ? "default" : "outline"
                        }
                        size="sm"
                        onClick={() => handleGroupChange(groupId)}
                        title={
                          activeSearch.group === groupId
                            ? t("serverBrowser.allGroups")
                            : t("serverBrowser.filterGroup", {
                                group:
                                  groupId === UNASSIGNED_SERVER_GROUP_ID
                                    ? t("serverBrowser.others")
                                    : group.name,
                              })
                        }
                      >
                        <span className="max-w-40 truncate">
                          {groupId === UNASSIGNED_SERVER_GROUP_ID
                            ? t("serverBrowser.others")
                            : group.name}
                        </span>
                        <span className="text-xs opacity-80">
                          ({group.playerCount})
                        </span>
                      </Button>
                    ))}
                  </div>
                ) : null}
                {regionOptions.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-2">
                    {regionOptions.map(([regionCode, regionCounts]) => {
                      const region =
                        regionsQuery.data?.find(
                          (option) => option.code === regionCode,
                        ) ?? null
                      return (
                        <Button
                          key={regionCode}
                          variant={
                            activeSearch.region === regionCode
                              ? "default"
                              : "outline"
                          }
                          size="sm"
                          onClick={() => handleRegionChange(regionCode)}
                        >
                          <div className="flex items-center gap-2 whitespace-nowrap">
                            {regionCode === "RU" ? (
                              <span className="flex min-w-0 items-center gap-2">
                                <CountryFlag
                                  countryCode="RU"
                                  showTooltip={false}
                                />
                                <span className="truncate">{regionCode}</span>
                              </span>
                            ) : (
                              <RegionBadge
                                regionCode={regionCode}
                                regionName={region?.name}
                              />
                            )}
                            <span className="text-xs opacity-80">
                              ({regionCounts.playerCount})
                            </span>
                          </div>
                        </Button>
                      )
                    })}
                  </div>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-2 lg:ml-auto">
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <button
                    type="button"
                    className={cn(
                      "flex h-8 items-center gap-2 rounded-md border px-2.5 shadow-xs transition-colors outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      activeSearch.status === "online" &&
                        "border-green-600/30 bg-green-600/5",
                    )}
                    onClick={() =>
                      handleSearchPatch({
                        status:
                          activeSearch.status === "online"
                            ? "offline"
                            : "online",
                      })
                    }
                    title={t("serverBrowser.switchStatus")}
                  >
                    <Switch
                      aria-hidden="true"
                      checked={activeSearch.status === "online"}
                      className="pointer-events-none"
                      tabIndex={-1}
                    />
                    <span
                      className={cn(
                        "text-xs font-medium",
                        activeSearch.status === "online" &&
                          "text-green-700 dark:text-green-400",
                      )}
                    >
                      {t("serverBrowser.online")}
                    </span>
                  </button>
                  <Button
                    type="button"
                    variant={activeSearch.hide_empty ? "default" : "outline"}
                    size="sm"
                    aria-pressed={activeSearch.hide_empty}
                    onClick={() =>
                      handleSearchPatch({
                        hide_empty: !activeSearch.hide_empty,
                        hide_occupied: false,
                      })
                    }
                    title={t("serverBrowser.hideEmptyTooltip")}
                  >
                    {t("serverBrowser.hideEmpty")}
                  </Button>
                  <Button
                    type="button"
                    variant={activeSearch.hide_occupied ? "default" : "outline"}
                    size="sm"
                    aria-pressed={activeSearch.hide_occupied}
                    onClick={() =>
                      handleSearchPatch({
                        hide_occupied: !activeSearch.hide_occupied,
                        hide_empty: false,
                      })
                    }
                    title={t("serverBrowser.hideOccupiedTooltip")}
                  >
                    {t("serverBrowser.hideOccupied")}
                  </Button>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <AddServerButton onServerAdded={handleServerAdded} />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    onClick={() => setMapDialogOpen(true)}
                    disabled={servers.length === 0}
                    aria-label={t("serverBrowser.openMap")}
                    title={t("serverBrowser.openMap")}
                    data-testid="open-servers-map-button"
                  >
                    <MapIcon className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    onClick={handleDownloadConfig}
                    disabled={sortedServers.length === 0}
                    aria-label={t("serverBrowser.downloadConfig")}
                    title={t("serverBrowser.downloadConfig")}
                    data-testid="download-servers-config-button"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    onClick={handleCopyShareLink}
                    aria-label={t("serverBrowser.share")}
                    title={t("serverBrowser.share")}
                    data-testid="share-servers-button"
                  >
                    <Share2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {sortedServers.length === 0 ? (
          <Card className={SERVER_BROWSER_CARD_CLASS_NAME}>
            <CardContent className="px-6 py-16 text-center text-muted-foreground">
              {t("serverBrowser.empty")}
            </CardContent>
          </Card>
        ) : activeSearch.view === "table" ? (
          <Card className={SERVER_BROWSER_CARD_CLASS_NAME}>
            <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
              <ServerTable
                servers={sortedServers}
                selectedAddress={selectedAddress}
                sortKey={activeSearch.sort}
                sortDirection={activeSearch.dir}
                onSortChange={handleSortChange}
                onSelect={handleSelectServer}
                onCopyAddress={handleCopyAddress}
                onSteamConnect={handleSteamConnect}
                mapDownloadUrls={mapDownloadUrls}
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
                  active={activeSearch.sort === "hostname"}
                  direction={activeSearch.dir}
                  label={t("serverBrowser.server")}
                  onClick={() => handleSortChange("hostname")}
                />
                <SortControl
                  active={activeSearch.sort === "map"}
                  direction={activeSearch.dir}
                  label={t("serverBrowser.map")}
                  onClick={() => handleSortChange("map")}
                />
                <SortControl
                  active={activeSearch.sort === "tier"}
                  direction={activeSearch.dir}
                  label={t("serverBrowser.tier")}
                  onClick={() => handleSortChange("tier")}
                />
                <SortControl
                  active={activeSearch.sort === "players"}
                  direction={activeSearch.dir}
                  label={t("serverBrowser.players")}
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
                  mapDownloadUrl={
                    getServerMapName(server)
                      ? mapDownloadUrls.get(
                          getServerMapName(server)?.toLowerCase() ?? "",
                        )
                      : undefined
                  }
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
            to: selectedGroupReturnPath ?? "/servers",
            replace: true,
          })
        }}
        onCopyAddress={handleCopyAddress}
        onSteamConnect={handleSteamConnect}
      />
      <ServerWorldMapDialog
        open={mapDialogOpen}
        servers={servers}
        onOpenChange={setMapDialogOpen}
        onSelectServer={(server) => {
          setMapDialogOpen(false)
          handleSelectServer(server)
        }}
      />
      <Dialog open={configDialogOpen} onOpenChange={setConfigDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("serverBrowser.configTitle")}</DialogTitle>
            <DialogDescription>
              {t("serverBrowser.configDescription")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p>
              <Trans
                i18nKey="serverBrowser.configPlace"
                values={{ filename: SERVER_CONFIG_FILENAME }}
                components={{ file: <code />, folder: <code /> }}
              />
            </p>
            <p>
              <Trans
                i18nKey="serverBrowser.configRun"
                values={{ filename: SERVER_CONFIG_FILENAME }}
                components={{ command: <code />, autoexec: <code /> }}
              />
            </p>
            <p>
              <Trans
                i18nKey="serverBrowser.configConnect"
                components={{
                  first: <code />,
                  second: <code />,
                  third: <code />,
                }}
              />
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
