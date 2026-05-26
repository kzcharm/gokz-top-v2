import { useQuery } from "@tanstack/react-query"
import { Plus, Search, ShieldAlert, X } from "lucide-react"
import { useEffect, useState } from "react"

import { OpenAPI } from "@/client/core/OpenAPI"
import { useAdminMode } from "@/components/admin-mode-provider"
import { DataTable } from "@/components/Common/DataTable"
import { PlayerSearchSelect } from "@/components/Common/PlayerSearchSelect"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import useAuth from "@/hooks/useAuth"
import type { GraphqlPlayer } from "@/lib/player-graphql"
import { canModerateBansAndRecords } from "@/lib/user-roles"
import { cn } from "@/lib/utils"
import { extractErrorMessage } from "@/utils"

import { AddBanDialog } from "./AddBanDialog"
import { type BanRow, getBanColumns } from "./columns"
import { EditBanDialog } from "./EditBanDialog"

type BansResponse = {
  count: number
  data: BanRow[]
}

const DEFAULT_PAGE_SIZE = 20

async function fetchBans({
  pageIndex,
  pageSize,
  q,
  steamid64,
}: {
  pageIndex: number
  pageSize: number
  q?: string | null
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
  const response = await fetch(`${OpenAPI.BASE}/v1/bans?${params.toString()}`, {
    credentials: OpenAPI.CREDENTIALS,
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  })
  if (!response.ok) {
    throw new Error("Failed to load bans")
  }

  return (await response.json()) as BansResponse
}

export function BansPage({
  initialSearchQuery,
}: {
  initialSearchQuery: string
}) {
  const { user } = useAuth()
  const { enabled: adminModeEnabled } = useAdminMode()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [expandedBanUuid, setExpandedBanUuid] = useState<string | null>(null)
  const [addBanDialogOpen, setAddBanDialogOpen] = useState(false)
  const [editBanDialogOpen, setEditBanDialogOpen] = useState(false)
  const [editingBan, setEditingBan] = useState<BanRow | null>(null)
  const [searchQuery, setSearchQuery] = useState(initialSearchQuery)
  const [selectedPlayer, setSelectedPlayer] = useState<GraphqlPlayer | null>(
    null,
  )
  const normalizedSearchQuery = searchQuery.trim()

  const bansQuery = useQuery({
    queryKey: [
      "bans",
      pageIndex,
      pageSize,
      selectedPlayer?.steamid64 ?? null,
      normalizedSearchQuery || null,
    ],
    queryFn: () =>
      fetchBans({
        pageIndex,
        pageSize,
        q: normalizedSearchQuery || null,
        steamid64: selectedPlayer?.steamid64 ?? null,
      }),
    staleTime: 30_000,
  })

  useEffect(() => {
    setSearchQuery(initialSearchQuery)
  }, [initialSearchQuery])

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
  const totalCount = bansQuery.data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize))
  const canAddBan = canModerateBansAndRecords(user)
  const showUpdaterColumn = canAddBan
  const showEditActions = canAddBan && adminModeEnabled
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

  const handleSearchQueryChange = (query: string) => {
    setSearchQuery(query)
    const normalized = query.trim()
    const nextUrl = normalized
      ? `/bans?q=${encodeURIComponent(normalized)}`
      : "/bans"
    window.history.replaceState(null, "", nextUrl)
    setPageIndex(0)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Bans</h1>
        {canAddBan ? (
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

      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 sm:px-8 sm:pt-8 sm:pb-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
            <div className="relative w-full lg:max-w-[22rem]">
              <Search className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-3 size-4 text-muted-foreground" />
              <Input
                aria-label="Search bans"
                className="pr-9 pl-9"
                placeholder="Search bans ..."
                value={searchQuery}
                onChange={(event) => handleSearchQueryChange(event.target.value)}
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
