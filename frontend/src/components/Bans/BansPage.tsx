import { useQuery } from "@tanstack/react-query"
import { Plus, Search, ShieldAlert, X } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { FaDiscord, FaQq } from "react-icons/fa"

import { OpenAPI } from "@/client/core/OpenAPI"
import {
  useAdminMode,
  useAdminModeSurface,
} from "@/components/admin-mode-provider"
import { DataTable } from "@/components/Common/DataTable"
import { PlayerSearchSelect } from "@/components/Common/PlayerSearchSelect"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useAuth from "@/hooks/useAuth"
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"
import { COMMUNITY_LINKS } from "@/lib/community-links"
import type { GraphqlPlayer } from "@/lib/player-graphql"
import { canModerateBansAndRecords, isSuperuser } from "@/lib/user-roles"
import { cn } from "@/lib/utils"
import { extractErrorMessage } from "@/utils"

import { AddBanDialog } from "./AddBanDialog"
import { formatBanTypeLabel } from "./ban-status"
import { type BanRow, getBanColumns } from "./columns"
import { EditBanDialog } from "./EditBanDialog"

type BansResponse = {
  count: number
  data: BanRow[]
}

const DEFAULT_PAGE_SIZE = 20
const ALL_FILTER_VALUE = "all"

const BAN_TYPE_OPTIONS = [
  "ban_evasion",
  "bhop_hack",
  "bhop_macro",
  "boosting",
  "exploiting",
  "strafe_hack",
  "strafe_macro",
  "other",
] as const

const BAN_STATUS_OPTIONS = [
  { value: "permanent", label: "Permanent" },
  { value: "active", label: "Active" },
  { value: "expired", label: "Expired" },
  { value: "unbanned", label: "Unbanned" },
] as const

type BanStatusFilter = (typeof BAN_STATUS_OPTIONS)[number]["value"]
type ServerOption = { id: number; name?: string | null }

async function fetchBans({
  pageIndex,
  pageSize,
  q,
  banType,
  status,
  serverId,
  hasServer,
  steamid64,
}: {
  pageIndex: number
  pageSize: number
  q?: string | null
  banType?: string | null
  status?: BanStatusFilter | null
  serverId?: number | null
  hasServer?: boolean | null
  steamid64?: string | null
}) {
  const accessToken = localStorage.getItem("access_token")
  const params = new URLSearchParams({
    offset: `${pageIndex * pageSize}`,
    limit: `${pageSize}`,
  })
  if (steamid64) {
    params.set("steamid64", steamid64)
  }
  if (q?.trim()) {
    params.set("q", q.trim())
  }
  if (banType) {
    params.set("ban_types", banType)
  }
  if (status) {
    params.set("status", status)
  }
  if (serverId !== null && serverId !== undefined) {
    params.set("server_id", `${serverId}`)
  }
  if (hasServer !== null && hasServer !== undefined) {
    params.set("has_server", `${hasServer}`)
  }
  const response = await fetch(`${OpenAPI.BASE}/v1/bans?${params.toString()}`, {
    credentials: OpenAPI.CREDENTIALS,
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  })
  if (!response.ok) {
    throw new Error("Failed to load bans")
  }

  return (await response.json()) as BansResponse
}

async function fetchBanServers() {
  const response = await fetch(`${OpenAPI.BASE}/v0/servers?limit=10000`, {
    credentials: OpenAPI.CREDENTIALS,
  })
  if (!response.ok) {
    throw new Error("Failed to load ban servers")
  }

  return (await response.json()) as ServerOption[]
}

export function BansPage({
  initialBanType,
  initialSearchQuery,
  initialServerFilter,
  initialStatus,
}: {
  initialBanType: string
  initialSearchQuery: string
  initialServerFilter: number | "none" | null
  initialStatus: BanStatusFilter | ""
}) {
  const { i18n } = useTranslation()
  const { user } = useAuth()
  const { enabled: adminModeEnabled } = useAdminMode()
  const canModerateBans = canModerateBansAndRecords(user)
  useAdminModeSurface(canModerateBans)
  const reportLink =
    i18n.resolvedLanguage === "zh-CN"
      ? COMMUNITY_LINKS.qq
      : COMMUNITY_LINKS.discord
  const ReportIcon = i18n.resolvedLanguage === "zh-CN" ? FaQq : FaDiscord
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "gokz-page-size-bans",
    defaultPageSize: DEFAULT_PAGE_SIZE,
  })
  const [expandedBanUuid, setExpandedBanUuid] = useState<string | null>(null)
  const [addBanDialogOpen, setAddBanDialogOpen] = useState(false)
  const [editBanDialogOpen, setEditBanDialogOpen] = useState(false)
  const [editingBan, setEditingBan] = useState<BanRow | null>(null)
  const [banType, setBanType] = useState(initialBanType)
  const [searchQuery, setSearchQuery] = useState(initialSearchQuery)
  const [serverFilter, setServerFilter] = useState<number | "none" | null>(
    initialServerFilter,
  )
  const [status, setStatus] = useState<BanStatusFilter | "">(initialStatus)
  const [selectedPlayer, setSelectedPlayer] = useState<GraphqlPlayer | null>(
    null,
  )
  const normalizedSearchQuery = searchQuery.trim()

  const banServersQuery = useQuery({
    queryKey: ["ban-servers"],
    queryFn: fetchBanServers,
    staleTime: 5 * 60_000,
  })

  const bansQuery = useQuery({
    queryKey: [
      "bans",
      pageIndex,
      pageSize,
      selectedPlayer?.steamid64 ?? null,
      normalizedSearchQuery || null,
      banType || null,
      status || null,
      serverFilter,
    ],
    queryFn: () =>
      fetchBans({
        pageIndex,
        pageSize,
        q: normalizedSearchQuery || null,
        banType: banType || null,
        status: status || null,
        serverId: typeof serverFilter === "number" ? serverFilter : null,
        hasServer: serverFilter === "none" ? false : null,
        steamid64: selectedPlayer?.steamid64 ?? null,
      }),
    staleTime: 30_000,
  })

  useEffect(() => {
    setSearchQuery(initialSearchQuery)
  }, [initialSearchQuery])

  useEffect(() => {
    setBanType(initialBanType)
  }, [initialBanType])

  useEffect(() => {
    setStatus(initialStatus)
  }, [initialStatus])

  useEffect(() => {
    setServerFilter(initialServerFilter)
  }, [initialServerFilter])

  useEffect(() => {
    const result = bansQuery.data
    if (
      normalizedSearchQuery &&
      result?.count === 1 &&
      result.data.length === 1
    ) {
      setExpandedBanUuid(result.data[0].uuid)
      return
    }

    setExpandedBanUuid(null)
  }, [bansQuery.data, normalizedSearchQuery])

  if (bansQuery.isError) {
    return (
      <Alert variant="destructive">
        <ShieldAlert />
        <AlertTitle>Unable to load bans</AlertTitle>
        <AlertDescription className="gap-3">
          <p>{extractErrorMessage(bansQuery.error)}</p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void bansQuery.refetch()
            }}
          >
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    )
  }

  const bans = bansQuery.data?.data ?? []
  const banServers = banServersQuery.data ?? []
  const selectedServerIsLoaded =
    typeof serverFilter === "number" &&
    banServers.some((server) => server.id === serverFilter)
  const totalCount = bansQuery.data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize))
  const canAdministerBans = adminModeEnabled && canModerateBans
  const showUpdaterColumn = canModerateBans
  const showEditActions = canAdministerBans
  const columns = getBanColumns({
    showUpdaterColumn,
    showEditActions,
    onEditBan: (ban) => {
      setEditingBan(ban)
      setEditBanDialogOpen(true)
    },
  })

  const handleSelectPlayer = (player: GraphqlPlayer) => {
    setSelectedPlayer(player)
    setPageIndex(0)
  }

  const clearSelectedPlayer = () => {
    setSelectedPlayer(null)
    setPageIndex(0)
  }

  const updateFiltersUrl = ({
    nextBanType = banType,
    nextSearchQuery = searchQuery,
    nextServerFilter = serverFilter,
    nextStatus = status,
  }: {
    nextBanType?: string
    nextSearchQuery?: string
    nextServerFilter?: number | "none" | null
    nextStatus?: BanStatusFilter | ""
  }) => {
    const params = new URLSearchParams()
    const normalizedSearchQuery = nextSearchQuery.trim()
    if (normalizedSearchQuery) {
      params.set("q", normalizedSearchQuery)
    }
    if (nextBanType) {
      params.set("banType", nextBanType)
    }
    if (nextStatus) {
      params.set("status", nextStatus)
    }
    if (nextServerFilter !== null) {
      params.set("serverId", `${nextServerFilter}`)
    }
    const query = params.toString()
    window.history.replaceState(null, "", query ? `/bans?${query}` : "/bans")
  }

  const handleSearchQueryChange = (query: string) => {
    setSearchQuery(query)
    updateFiltersUrl({ nextSearchQuery: query })
    setPageIndex(0)
  }

  const handleBanTypeChange = (value: string) => {
    const nextBanType = value === ALL_FILTER_VALUE ? "" : value
    setBanType(nextBanType)
    updateFiltersUrl({ nextBanType })
    setPageIndex(0)
  }

  const handleStatusChange = (value: string) => {
    const nextStatus =
      value === ALL_FILTER_VALUE ? "" : (value as BanStatusFilter)
    setStatus(nextStatus)
    updateFiltersUrl({ nextStatus })
    setPageIndex(0)
  }

  const handleServerChange = (value: string) => {
    const nextServerFilter =
      value === ALL_FILTER_VALUE
        ? null
        : value === "none"
          ? "none"
          : Number(value)
    setServerFilter(nextServerFilter)
    updateFiltersUrl({ nextServerFilter })
    setPageIndex(0)
  }

  const clearFilters = () => {
    setSearchQuery("")
    setBanType("")
    setStatus("")
    setServerFilter(null)
    setSelectedPlayer(null)
    setPageIndex(0)
    window.history.replaceState(null, "", "/bans")
  }

  const hasActiveFilters = Boolean(
    normalizedSearchQuery ||
      banType ||
      status ||
      serverFilter !== null ||
      selectedPlayer,
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Bans</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            asChild
            type="button"
            className="bg-yellow-500 text-white hover:bg-yellow-500/90 focus-visible:ring-yellow-500/30 dark:bg-yellow-500 dark:text-white dark:hover:bg-yellow-400"
          >
            <a href={reportLink} target="_blank" rel="noreferrer">
              <ReportIcon className="size-4" />
              Report
            </a>
          </Button>
          {canAdministerBans ? (
            <Button
              type="button"
              variant="destructive"
              onClick={() => setAddBanDialogOpen(true)}
            >
              <Plus className="size-4" />
              Add Ban
            </Button>
          ) : null}
        </div>
      </div>

      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 sm:px-8 sm:pt-8 sm:pb-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-center">
            <div className="relative w-full lg:max-w-[22rem]">
              <Search className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-3 size-4 text-muted-foreground" />
              <Input
                aria-label="Search bans"
                className="pr-9 pl-9"
                placeholder="Search bans ..."
                value={searchQuery}
                onChange={(event) =>
                  handleSearchQueryChange(event.target.value)
                }
              />
              {searchQuery ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="-translate-y-1/2 absolute top-1/2 right-1 size-7"
                  aria-label="Clear ban search"
                  onClick={() => handleSearchQueryChange("")}
                >
                  <X className="size-4" />
                </Button>
              ) : null}
            </div>
            <div className="w-full lg:max-w-[18rem]">
              <PlayerSearchSelect
                ariaLabel="Search players"
                clearButtonLabel="Clear player filter"
                placeholder="Search player ..."
                searchQueryKey="bans-page"
                selectedPlayer={selectedPlayer}
                onSelectPlayer={handleSelectPlayer}
                onClearPlayer={clearSelectedPlayer}
              />
            </div>
            <Select
              value={banType || ALL_FILTER_VALUE}
              onValueChange={handleBanTypeChange}
            >
              <SelectTrigger
                aria-label="Filter by ban type"
                className={cn(
                  "w-full lg:w-44",
                  !banType && "text-muted-foreground",
                )}
              >
                <SelectValue placeholder="All Ban Types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_FILTER_VALUE}>All Ban Types</SelectItem>
                {BAN_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {formatBanTypeLabel(option)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={status || ALL_FILTER_VALUE}
              onValueChange={handleStatusChange}
            >
              <SelectTrigger
                aria-label="Filter by ban status"
                className={cn(
                  "w-full lg:w-40",
                  !status && "text-muted-foreground",
                )}
              >
                <SelectValue placeholder="All Statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_FILTER_VALUE}>All Statuses</SelectItem>
                {BAN_STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={
                serverFilter === null ? ALL_FILTER_VALUE : `${serverFilter}`
              }
              onValueChange={handleServerChange}
            >
              <SelectTrigger
                aria-label="Filter by server"
                className={cn(
                  "w-full lg:w-52",
                  serverFilter === null && "text-muted-foreground",
                )}
              >
                <SelectValue placeholder="All Servers" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_FILTER_VALUE}>All Servers</SelectItem>
                <SelectItem value="none">No Server</SelectItem>
                {typeof serverFilter === "number" && !selectedServerIsLoaded ? (
                  <SelectItem value={`${serverFilter}`}>
                    Server {serverFilter}
                  </SelectItem>
                ) : null}
                {banServers.map((server) => (
                  <SelectItem key={server.id} value={`${server.id}`}>
                    {server.name?.trim() || `Server ${server.id}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant="outline"
              className="w-full lg:w-auto"
              aria-label="Clear ban filters"
              disabled={!hasActiveFilters}
              onClick={clearFilters}
            >
              <X className="size-4" />
              Clear Filters
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="gap-0 overflow-hidden rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-b-none">
          <DataTable
            columns={columns}
            data={bans}
            isLoading={bansQuery.isLoading}
            emptyText="No bans found."
            showFooter={false}
            getRowId={(row) => row.uuid}
            expandedRowId={expandedBanUuid}
            getRowProps={(row) => {
              const isExpanded = expandedBanUuid === row.uuid
              return {
                className: cn(
                  "cursor-pointer",
                  isExpanded && "bg-muted/25 hover:bg-muted/25",
                ),
                onClick: () => {
                  setExpandedBanUuid((currentId) =>
                    currentId === row.uuid ? null : row.uuid,
                  )
                },
              }
            }}
            renderExpandedContent={(row) => (
              <div className="rounded-lg border bg-background/70 p-3">
                <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-6 text-foreground">
                  {row.stats?.trim() || "No detail stats available."}
                </pre>
              </div>
            )}
            serverPagination={{
              pageIndex,
              pageSize,
              totalCount,
              onPageChange: setPageIndex,
              onPageSizeChange: (nextPageSize) => {
                setPageSize(nextPageSize)
                setPageIndex(0)
              },
            }}
          />
          <TablePaginationFooter
            totalLabel="Bans"
            totalCount={totalCount}
            pageIndex={pageIndex}
            pageCount={pageCount}
            pageSize={pageSize}
            onPageIndexChange={setPageIndex}
            onPageSizeChange={(nextPageSize) => {
              setPageSize(nextPageSize)
              setPageIndex(0)
            }}
          />
        </CardContent>
      </Card>

      <AddBanDialog
        open={addBanDialogOpen}
        onOpenChange={setAddBanDialogOpen}
      />
      <EditBanDialog
        ban={editingBan}
        canDeleteLocalBan={isSuperuser(user)}
        open={editBanDialogOpen}
        onOpenChange={(open) => {
          setEditBanDialogOpen(open)
          if (!open) {
            setEditingBan(null)
          }
        }}
      />
    </div>
  )
}
