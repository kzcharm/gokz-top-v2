import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  createFileRoute,
  Link,
  redirect,
  useRouterState,
} from "@tanstack/react-router"
import {
  type ColumnDef,
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import {
  ArrowDown,
  ArrowUp,
  Check,
  Copy,
  Download,
  Github,
  KeyRound,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  X,
} from "lucide-react"
import { useCallback, useEffect, useId, useMemo, useState } from "react"

import {
  type AdminServerAccessPublic,
  type AdminServerGroupPublic,
  AdminServersService,
  type ApiError,
  OpenAPI,
  type ServerGlobalapiAdminPublic,
  type ServerPublic,
  UsersService,
} from "@/client"
import {
  AdminControlsCard,
  AdminTableCard,
} from "@/components/Admin/AdminPageLayout"
import { CountryFlag } from "@/components/Common/CountryFlag"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import {
  PlayerDisplay,
  type PlayerDisplayPlayer,
} from "@/components/Common/PlayerDisplay"
import { PlayerSearchSelect } from "@/components/Common/PlayerSearchSelect"
import { RegionFlag } from "@/components/Common/RegionFlag"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { isLoggedIn } from "@/hooks/useAuth"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import useCustomToast from "@/hooks/useCustomToast"
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"
import { getPageTitle } from "@/lib/site"
import { isSuperuser } from "@/lib/user-roles"
import { extractErrorMessage } from "@/utils"

const NO_GROUP = "__none"
const GOKZ_TOP_PLUGINS_URL = "https://github.com/kzcharm/gokz-top-plugins"
type GlobalApiSortBy = "id" | "server" | "updated_at" | "created_at"
type ServerGroupSortBy =
  | "name"
  | "last_api_key_used_at"
  | "created_at"
  | "updated_at"

async function downloadGokzLocalDbRecords(serverIds: number[]) {
  const params = new URLSearchParams()
  for (const serverId of [...serverIds].sort((a, b) => a - b)) {
    params.append("server_id", String(serverId))
  }
  const accessToken = localStorage.getItem("access_token")
  const response = await fetch(
    `${OpenAPI.BASE}/v1/admin/servers/globalapi/records/export?${params.toString()}`,
    {
      headers: accessToken
        ? { Authorization: `Bearer ${accessToken}` }
        : undefined,
    },
  )
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail =
      payload && typeof payload.detail === "string"
        ? payload.detail
        : "Unable to export GOKZ LocalDB records."
    throw new Error(detail)
  }

  const disposition = response.headers.get("content-disposition")
  const filename =
    disposition?.match(/filename="([^"]+)"/)?.[1] ??
    "gokz-localdb-records.sql.gz"
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

const ADMIN_SERVER_TAB_OPTIONS = [
  {
    value: "public",
    label: "Public Server",
    to: "/admin/servers/public-server",
  },
  {
    value: "groups",
    label: "Server Group",
    to: "/admin/servers/server-group",
  },
  {
    value: "globalapi",
    label: "GlobalAPI Server",
    to: "/admin/servers/globalapi-server",
  },
] as const

export const Route = createFileRoute("/_layout/admin/servers")({
  component: AdminServers,
  beforeLoad: async ({ location }) => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
    const user = await UsersService.readUserMe().catch(() => {
      localStorage.removeItem("access_token")
      throw redirect({ to: "/login" })
    })
    if (location.pathname === "/admin/servers") {
      throw redirect({ to: "/admin/servers/globalapi-server" })
    }
    if (isSuperuser(user)) {
      return
    }
    await AdminServersService.readAdminServerAccess().catch(() => {
      throw redirect({ to: "/" })
    })
  },
  head: () => ({
    meta: [
      {
        title: getPageTitle("Admin Servers"),
      },
    ],
  }),
})

function AdminServers() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const activeTab =
    ADMIN_SERVER_TAB_OPTIONS.find((tab) => pathname.startsWith(tab.to))
      ?.value ?? "globalapi"
  const accessQuery = useQuery({
    queryKey: ["admin-servers-access"],
    queryFn: () => AdminServersService.readAdminServerAccess(),
  })
  const groupsQuery = useQuery({
    queryKey: ["admin-server-groups", "options"],
    queryFn: () => AdminServersService.readAdminServerGroups({ limit: 1000 }),
    enabled: activeTab !== "groups",
  })

  const access = accessQuery.data
  const groups = groupsQuery.data?.data ?? []

  return (
    <Tabs
      value={activeTab}
      className="flex w-full max-w-full min-w-0 flex-col gap-6"
    >
      <TabsList className="h-auto w-full flex-wrap justify-start border border-border bg-background/60 sm:w-fit">
        {ADMIN_SERVER_TAB_OPTIONS.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value} asChild>
            <Link to={tab.to}>{tab.label}</Link>
          </TabsTrigger>
        ))}
      </TabsList>

      {activeTab === "globalapi" ? (
        <GlobalApiServersTab
          access={access}
          groups={groups}
          groupsLoading={groupsQuery.isLoading}
        />
      ) : null}
      {activeTab === "public" ? (
        <PublicServersTab access={access} groups={groups} />
      ) : null}
      {activeTab === "groups" ? (
        <ServerGroupsTab canEditOwner={access?.role === "root_admin"} />
      ) : null}
    </Tabs>
  )
}

export function GlobalApiServersTab({
  access,
  groups,
  groupsLoading,
}: {
  access: AdminServerAccessPublic | undefined
  groups: AdminServerGroupPublic[]
  groupsLoading: boolean
}) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "gokz-page-size-admin-globalapi-servers",
  })
  const [search, setSearch] = useState("")
  const [approvalFilter, setApprovalFilter] = useState("1")
  const [editingServer, setEditingServer] =
    useState<ServerGlobalapiAdminPublic | null>(null)
  const [selectedServerIds, setSelectedServerIds] = useState<Set<number>>(
    () => new Set(),
  )
  const [sorting, setSorting] = useState<SortingState>([
    { id: "id", desc: true },
  ])
  const canApprove = access?.can_approve_servers ?? false
  const canEditOwner = access?.role === "root_admin"
  const groupNamesById = useMemo(
    () => new Map(groups.map((group) => [group.id, group.name])),
    [groups],
  )
  const activeSort = sorting[0] ?? { id: "id", desc: true }
  const sortBy: GlobalApiSortBy =
    activeSort.id === "id" ||
    activeSort.id === "server" ||
    activeSort.id === "updated_at" ||
    activeSort.id === "created_at"
      ? activeSort.id
      : "id"
  const sortOrder = activeSort.desc ? "desc" : "asc"

  const query = useQuery({
    queryKey: [
      "admin-globalapi-servers",
      pageIndex,
      pageSize,
      search,
      approvalFilter,
      sortBy,
      sortOrder,
    ],
    queryFn: () =>
      AdminServersService.readAdminGlobalapiServers({
        offset: pageIndex * pageSize,
        limit: pageSize,
        q: search.trim() || undefined,
        approvalStatus:
          approvalFilter === "all" ? undefined : Number(approvalFilter),
        sortBy,
        sortOrder,
      }),
  })

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    const nextSort = next.length > 0 ? [next[0]] : [{ id: "id", desc: true }]
    setSorting(nextSort)
    setPageIndex(0)
  }

  const updateMutation = useMutation({
    mutationFn: ({
      serverId,
      groupId,
      name,
      ownerSteamid64,
      approvalStatus,
    }: {
      serverId: number
      groupId?: string | null
      name?: string | null
      ownerSteamid64?: string | null
      approvalStatus?: number
    }) =>
      AdminServersService.updateAdminGlobalapiServer({
        serverId,
        requestBody: {
          ...(groupId !== undefined ? { group_id: groupId } : {}),
          ...(name !== undefined ? { name } : {}),
          ...(ownerSteamid64 !== undefined
            ? { owner_steamid64: ownerSteamid64 }
            : {}),
          ...(approvalStatus !== undefined
            ? { approval_status: approvalStatus }
            : {}),
        },
      }),
    onSuccess: () => {
      showSuccessToast("GlobalAPI server updated.")
      void queryClient.invalidateQueries({
        queryKey: ["admin-globalapi-servers"],
      })
    },
    onError: (error: ApiError) => showErrorToast(extractErrorMessage(error)),
  })
  const downloadMutation = useMutation({
    mutationFn: downloadGokzLocalDbRecords,
    onSuccess: () => {
      showSuccessToast("GOKZ LocalDB record export downloaded.")
    },
    onError: (error: Error) => showErrorToast(error.message),
  })

  const visibleServerIds = useMemo(
    () => (query.data?.data ?? []).map((server) => server.id),
    [query.data?.data],
  )
  const selectedVisibleCount = visibleServerIds.filter((serverId) =>
    selectedServerIds.has(serverId),
  ).length
  const allVisibleSelected =
    visibleServerIds.length > 0 &&
    selectedVisibleCount === visibleServerIds.length

  const columns = useMemo<ColumnDef<ServerGlobalapiAdminPublic>[]>(
    () => [
      {
        id: "select",
        size: 44,
        header: () => (
          <Checkbox
            aria-label="Select all visible GlobalAPI servers"
            checked={
              allVisibleSelected
                ? true
                : selectedVisibleCount > 0
                  ? "indeterminate"
                  : false
            }
            onCheckedChange={(checked) => {
              setSelectedServerIds((current) => {
                const next = new Set(current)
                for (const serverId of visibleServerIds) {
                  if (checked) {
                    next.add(serverId)
                  } else {
                    next.delete(serverId)
                  }
                }
                return next
              })
            }}
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            aria-label={`Select GlobalAPI server ${row.original.id}`}
            checked={selectedServerIds.has(row.original.id)}
            onCheckedChange={(checked) => {
              setSelectedServerIds((current) => {
                const next = new Set(current)
                if (checked) {
                  next.add(row.original.id)
                } else {
                  next.delete(row.original.id)
                }
                return next
              })
            }}
          />
        ),
      },
      {
        accessorKey: "id",
        header: ({ column }) => <SortableHeader column={column} label="ID" />,
        cell: ({ row }) => (
          <span className="font-mono text-sm">{row.original.id}</span>
        ),
      },
      {
        id: "server",
        accessorKey: "name",
        header: ({ column }) => (
          <SortableHeader column={column} label="Server" />
        ),
        cell: ({ row }) => (
          <div className="min-w-56">
            <div
              className="max-w-72 truncate font-medium"
              title={row.original.name || "Unnamed"}
            >
              {row.original.name || "Unnamed"}
            </div>
          </div>
        ),
      },
      {
        accessorKey: "owner_steamid64",
        header: "Owner",
        cell: ({ row }) => (
          <PlayerDisplay
            fallbackSteamid64={row.original.owner_steamid64 ?? undefined}
            nameMaxLength={22}
          />
        ),
      },
      {
        accessorKey: "group_id",
        header: "Group",
        cell: ({ row }) => (
          <span className="text-sm">
            {row.original.group_id
              ? (groupNamesById.get(row.original.group_id) ?? "Unknown Group")
              : "--"}
          </span>
        ),
      },
      {
        accessorKey: "created_at",
        header: ({ column }) => (
          <SortableHeader column={column} label="Created" />
        ),
        cell: ({ row }) => (
          <FormattedDateTime value={row.original.created_at} />
        ),
      },
      {
        accessorKey: "updated_at",
        header: ({ column }) => (
          <SortableHeader column={column} label="Updated" />
        ),
        cell: ({ row }) => (
          <FormattedDateTime value={row.original.updated_at} />
        ),
      },
      {
        accessorKey: "approval_status",
        header: "Approval",
        cell: ({ row }) => (
          <ApprovalStatusBadge status={row.original.approval_status} />
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Edit GlobalAPI server"
              onClick={() => setEditingServer(row.original)}
            >
              <Pencil />
            </Button>
          </div>
        ),
      },
    ],
    [
      allVisibleSelected,
      groupNamesById,
      selectedServerIds,
      selectedVisibleCount,
      visibleServerIds,
    ],
  )

  return (
    <div className="flex flex-col gap-4">
      <AdminControlsCard>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <Input
            className="sm:max-w-sm"
            placeholder="Search GlobalAPI servers..."
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setPageIndex(0)
            }}
          />
          <Select
            value={approvalFilter}
            onValueChange={(value) => {
              setApprovalFilter(value)
              setPageIndex(0)
            }}
          >
            <SelectTrigger className="w-full sm:w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All approvals</SelectItem>
              <SelectItem value="1">Approved</SelectItem>
              <SelectItem value="0">Pending</SelectItem>
            </SelectContent>
          </Select>
          <LoadingButton
            type="button"
            variant="outline"
            loading={downloadMutation.isPending}
            disabled={selectedServerIds.size === 0}
            onClick={() =>
              downloadMutation.mutate(Array.from(selectedServerIds))
            }
          >
            <Download />
            Export records
            {selectedServerIds.size > 0 ? ` (${selectedServerIds.size})` : ""}
          </LoadingButton>
        </div>
      </AdminControlsCard>
      <AdminTableCard>
        <DataTable
          columns={columns}
          data={query.data?.data ?? []}
          isLoading={query.isLoading}
          stickyHeader
          stickyHeaderTopClassName="top-16"
          tableContainerClassName="md:overflow-visible"
          tableClassName="border-separate border-spacing-0"
          showFooter={false}
          emptyText="No GlobalAPI servers found."
          serverPagination={{
            pageIndex,
            pageSize,
            totalCount: query.data?.count ?? 0,
            onPageChange: setPageIndex,
            onPageSizeChange: (size) => {
              setPageSize(size)
              setPageIndex(0)
            },
          }}
          sorting={{
            state: sorting,
            onSortingChange,
            manualSorting: true,
          }}
        />
        <TablePaginationFooter
          totalLabel="Servers"
          totalCount={query.data?.count ?? 0}
          pageIndex={pageIndex}
          pageCount={Math.max(
            1,
            Math.ceil((query.data?.count ?? 0) / pageSize),
          )}
          pageSize={pageSize}
          onPageIndexChange={setPageIndex}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPageIndex(0)
          }}
          hasExactCount={!query.isLoading}
          isTotalCountLoading={query.isLoading}
        />
      </AdminTableCard>
      <GlobalApiServerDialog
        server={editingServer}
        groups={groups}
        groupsLoading={groupsLoading}
        canEditOwner={canEditOwner}
        canEditApproval={canApprove}
        open={editingServer !== null}
        loading={updateMutation.isPending}
        onOpenChange={(open) => {
          if (!open) {
            setEditingServer(null)
          }
        }}
        onSubmit={(input) => {
          updateMutation.mutate(input, {
            onSuccess: () => setEditingServer(null),
          })
        }}
      />
    </div>
  )
}

function GlobalApiServerDialog({
  server,
  groups,
  groupsLoading,
  canEditOwner,
  canEditApproval,
  open,
  loading,
  onOpenChange,
  onSubmit,
}: {
  server: ServerGlobalapiAdminPublic | null
  groups: AdminServerGroupPublic[]
  groupsLoading: boolean
  canEditOwner: boolean
  canEditApproval: boolean
  open: boolean
  loading: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (input: {
    serverId: number
    name: string | null
    ownerSteamid64?: string | null
    groupId: string | null
    approvalStatus?: number
  }) => void
}) {
  const [name, setName] = useState("")
  const [owner, setOwner] = useState<PlayerDisplayPlayer | null>(null)
  const [groupId, setGroupId] = useState(NO_GROUP)
  const [approvalStatus, setApprovalStatus] = useState("0")

  useEffect(() => {
    if (!open) {
      return
    }
    setName(server?.name ?? "")
    setOwner(
      server?.owner_steamid64 ? { steamid64: server.owner_steamid64 } : null,
    )
    setGroupId(server?.group_id ?? NO_GROUP)
    setApprovalStatus(String(server?.approval_status ?? 0))
  }, [open, server])

  const trimmedName = name.trim()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            Edit GlobalAPI Server{server ? ` #${server.id}` : ""}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <LabeledInput label="Name" value={name} onChange={setName} />
          <PlayerSearchSelect
            id="globalapi-server-owner"
            ariaLabel="Owner"
            label="Owner"
            placeholder="Search player ..."
            disabled={!canEditOwner || loading}
            searchQueryKey="globalapi-server-owner"
            selectedPlayer={owner}
            onSelectPlayer={setOwner}
            onClearPlayer={() => setOwner(null)}
          />
          <div className="grid gap-2">
            <label
              className="text-sm font-medium"
              htmlFor="globalapi-server-group"
            >
              Group
            </label>
            <Select
              value={groupId}
              onValueChange={setGroupId}
              disabled={groupsLoading || loading}
            >
              <SelectTrigger id="globalapi-server-group">
                <SelectValue placeholder="Select a server group" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_GROUP}>--</SelectItem>
                {groups.map((group) => (
                  <SelectItem key={group.id} value={group.id}>
                    {group.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <label
              className="text-sm font-medium"
              htmlFor="globalapi-server-approval"
            >
              Approval Status
            </label>
            <Select
              value={approvalStatus}
              onValueChange={setApprovalStatus}
              disabled={!canEditApproval || loading}
            >
              <SelectTrigger id="globalapi-server-approval">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">Pending</SelectItem>
                <SelectItem value="1">Approved</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={loading}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <LoadingButton
            type="button"
            loading={loading}
            disabled={!server}
            onClick={() => {
              if (server) {
                onSubmit({
                  serverId: server.id,
                  name: trimmedName || null,
                  ...(canEditOwner
                    ? { ownerSteamid64: owner?.steamid64 ?? null }
                    : {}),
                  groupId: groupId === NO_GROUP ? null : groupId,
                  ...(canEditApproval
                    ? { approvalStatus: Number(approvalStatus) }
                    : {}),
                })
              }
            }}
          >
            <Save />
            Save
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ApprovalStatusBadge({ status }: { status: number }) {
  return status === 1 ? (
    <Badge className="border-green-200 bg-green-100 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-300">
      Approved
    </Badge>
  ) : (
    <Badge className="border-amber-200 bg-amber-100 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
      Pending
    </Badge>
  )
}

function SortableHeader({
  column,
  label,
}: {
  column: {
    getIsSorted: () => false | "asc" | "desc"
    toggleSorting: (desc?: boolean) => void
  }
  label: string
}) {
  const sorted = column.getIsSorted()
  return (
    <button
      type="button"
      className="-mx-2 -my-1 inline-flex items-center gap-1 rounded-md px-2 py-1 text-left text-sm font-medium hover:bg-accent"
      onClick={() => column.toggleSorting(sorted === "asc")}
    >
      {label}
      {sorted === "asc" ? <ArrowUp className="size-3" /> : null}
      {sorted === "desc" ? <ArrowDown className="size-3" /> : null}
    </button>
  )
}

export function PublicServersTab({
  access,
  groups,
}: {
  access: AdminServerAccessPublic | undefined
  groups: AdminServerGroupPublic[]
}) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "gokz-page-size-admin-public-servers",
  })
  const [search, setSearch] = useState("")
  const [groupFilter, setGroupFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [visibilityFilter, setVisibilityFilter] = useState("all")
  const [regionFilter, setRegionFilter] = useState("all")
  const [editingServerId, setEditingServerId] = useState<string | null>(null)
  const [draftGroupId, setDraftGroupId] = useState<string>(NO_GROUP)
  const [draftStatus, setDraftStatus] =
    useState<NonNullable<ServerPublic["status"]>>("enabled")
  const [draftIsPublic, setDraftIsPublic] = useState(true)
  const canClearGroup = access?.role !== "server_owner"

  const query = useQuery({
    queryKey: [
      "admin-public-servers",
      pageIndex,
      pageSize,
      search,
      groupFilter,
      statusFilter,
      visibilityFilter,
      regionFilter,
    ],
    queryFn: () =>
      AdminServersService.readAdminPublicServers({
        offset: pageIndex * pageSize,
        limit: pageSize,
        q: search.trim() || undefined,
        groupId:
          groupFilter === "all" || groupFilter === "ungrouped"
            ? undefined
            : groupFilter,
        ungrouped: groupFilter === "ungrouped" ? true : undefined,
        status:
          statusFilter === "all"
            ? undefined
            : (statusFilter as ServerPublic["status"]),
        isPublic:
          visibilityFilter === "all"
            ? undefined
            : visibilityFilter === "public",
        region: regionFilter === "all" ? undefined : regionFilter,
      }),
  })

  const updateMutation = useMutation({
    mutationFn: ({
      serverId,
      groupId,
      status,
      isPublic,
    }: {
      serverId: string
      groupId?: string | null
      status?: ServerPublic["status"]
      isPublic?: boolean
    }) =>
      AdminServersService.updateAdminPublicServer({
        serverId,
        requestBody: {
          ...(groupId !== undefined ? { group_id: groupId } : {}),
          ...(status !== undefined ? { status } : {}),
          ...(isPublic !== undefined ? { is_public: isPublic } : {}),
        },
      }),
    onSuccess: () => {
      showSuccessToast("Public server updated.")
      void queryClient.invalidateQueries({ queryKey: ["admin-public-servers"] })
    },
    onError: (error: ApiError) => showErrorToast(extractErrorMessage(error)),
  })

  const deleteMutation = useMutation({
    mutationFn: (serverId: string) =>
      AdminServersService.deleteAdminPublicServer({ serverId }),
    onSuccess: () => {
      showSuccessToast("Public server deleted.")
      void queryClient.invalidateQueries({ queryKey: ["admin-public-servers"] })
    },
    onError: (error: ApiError) => showErrorToast(extractErrorMessage(error)),
  })

  const columns = useMemo<ColumnDef<ServerPublic>[]>(
    () => [
      {
        id: "server_name",
        accessorFn: (server) => server.live_status?.hostname ?? "",
        header: "Server Name",
        cell: ({ row }) => (
          <span
            className="font-medium"
            title={row.original.live_status?.hostname ?? undefined}
          >
            {row.original.live_status?.hostname || "Unnamed server"}
          </span>
        ),
      },
      {
        accessorKey: "ip",
        header: "IP",
        cell: ({ row }) => (
          <span className="font-mono text-sm">
            {row.original.ip}:{row.original.port}
          </span>
        ),
      },
      {
        accessorKey: "group_id",
        header: "Group",
        cell: ({ row }) =>
          editingServerId === row.original.id ? (
            <Select value={draftGroupId} onValueChange={setDraftGroupId}>
              <SelectTrigger className="w-52">
                <SelectValue placeholder="No group" />
              </SelectTrigger>
              <SelectContent>
                {canClearGroup ? (
                  <SelectItem value={NO_GROUP}>No group</SelectItem>
                ) : null}
                {groups.map((group) => (
                  <SelectItem key={group.id} value={group.id}>
                    {group.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <span className="text-sm">
              {row.original.group?.name || "No group"}
            </span>
          ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) =>
          editingServerId === row.original.id ? (
            <Select
              value={draftStatus}
              onValueChange={(value) =>
                setDraftStatus(value as typeof draftStatus)
              }
            >
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="enabled">Enabled</SelectItem>
                <SelectItem value="invalid">Invalid</SelectItem>
                <SelectItem value="disabled">Disabled</SelectItem>
              </SelectContent>
            </Select>
          ) : (
            <ServerStatusBadge status={row.original.status} />
          ),
      },
      {
        accessorKey: "is_public",
        header: "Visibility",
        cell: ({ row }) =>
          editingServerId === row.original.id ? (
            <Select
              value={draftIsPublic ? "public" : "hidden"}
              onValueChange={(value) => setDraftIsPublic(value === "public")}
            >
              <SelectTrigger className="w-32" aria-label="Server visibility">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="public">Public</SelectItem>
                <SelectItem value="hidden">Hidden</SelectItem>
              </SelectContent>
            </Select>
          ) : (
            <ServerVisibilityBadge isPublic={row.original.is_public} />
          ),
      },
      {
        accessorKey: "country",
        header: "Location",
        cell: ({ row }) => (
          <div className="flex items-center gap-2 text-sm">
            <CountryFlag
              countryCode={row.original.country}
              showTooltip={false}
            />
            <span>{row.original.city || "Unknown"}</span>
          </div>
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) =>
          editingServerId === row.original.id ? (
            <div className="flex justify-end gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Save public server"
                disabled={updateMutation.isPending}
                onClick={() =>
                  updateMutation.mutate(
                    {
                      serverId: row.original.id,
                      groupId: draftGroupId === NO_GROUP ? null : draftGroupId,
                      status: draftStatus,
                      isPublic: draftIsPublic,
                    },
                    { onSuccess: () => setEditingServerId(null) },
                  )
                }
              >
                <Check />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Cancel editing"
                onClick={() => setEditingServerId(null)}
              >
                <X />
              </Button>
            </div>
          ) : (
            <div className="flex justify-end gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Edit public server"
                onClick={() => {
                  setEditingServerId(row.original.id)
                  setDraftGroupId(row.original.group_id ?? NO_GROUP)
                  setDraftStatus(row.original.status ?? "enabled")
                  setDraftIsPublic(row.original.is_public)
                }}
              >
                <Pencil />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="text-destructive hover:text-destructive"
                aria-label="Delete public server"
                disabled={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(row.original.id)}
              >
                <Trash2 />
              </Button>
            </div>
          ),
      },
    ],
    [
      canClearGroup,
      deleteMutation,
      draftGroupId,
      draftIsPublic,
      draftStatus,
      editingServerId,
      groups,
      updateMutation,
    ],
  )

  return (
    <div className="flex flex-col gap-4">
      <AdminControlsCard>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <Input
            className="sm:w-64"
            placeholder="Search servers..."
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setPageIndex(0)
            }}
          />
          <Select
            value={groupFilter}
            onValueChange={(value) => {
              setGroupFilter(value)
              setPageIndex(0)
            }}
          >
            <SelectTrigger className="w-full sm:w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All groups</SelectItem>
              <SelectItem value="ungrouped">No group</SelectItem>
              {groups.map((group) => (
                <SelectItem key={group.id} value={group.id}>
                  {group.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={statusFilter}
            onValueChange={(value) => {
              setStatusFilter(value)
              setPageIndex(0)
            }}
          >
            <SelectTrigger
              className="w-full sm:w-40"
              aria-label="Filter servers by status"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="enabled">
                <ServerStatusBadge status="enabled" />
              </SelectItem>
              <SelectItem value="invalid">
                <ServerStatusBadge status="invalid" />
              </SelectItem>
              <SelectItem value="disabled">
                <ServerStatusBadge status="disabled" />
              </SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={visibilityFilter}
            onValueChange={(value) => {
              setVisibilityFilter(value)
              setPageIndex(0)
            }}
          >
            <SelectTrigger
              className="w-full sm:w-40"
              aria-label="Filter servers by visibility"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All visibility</SelectItem>
              <SelectItem value="public">Public</SelectItem>
              <SelectItem value="hidden">Hidden</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={regionFilter}
            onValueChange={(value) => {
              setRegionFilter(value)
              setPageIndex(0)
            }}
          >
            <SelectTrigger className="w-full sm:w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All regions</SelectItem>
              {["AF", "AS", "CIS", "CN", "EU", "ME", "NA", "OC", "SA"].map(
                (region) => (
                  <SelectItem key={region} value={region}>
                    <RegionFlag regionCode={region} showTooltip={false} />
                    {region}
                  </SelectItem>
                ),
              )}
            </SelectContent>
          </Select>
        </div>
      </AdminControlsCard>
      <AdminTableCard>
        <DataTable
          columns={columns}
          data={query.data?.data ?? []}
          isLoading={query.isLoading}
          stickyHeader
          stickyHeaderTopClassName="top-16"
          tableContainerClassName="md:overflow-visible"
          tableClassName="border-separate border-spacing-0"
          showFooter={false}
          emptyText="No public servers found."
          serverPagination={{
            pageIndex,
            pageSize,
            totalCount: query.data?.count ?? 0,
            onPageChange: setPageIndex,
            onPageSizeChange: (size) => {
              setPageSize(size)
              setPageIndex(0)
            },
          }}
        />
        <TablePaginationFooter
          totalLabel="Servers"
          totalCount={query.data?.count ?? 0}
          pageIndex={pageIndex}
          pageCount={Math.max(
            1,
            Math.ceil((query.data?.count ?? 0) / pageSize),
          )}
          pageSize={pageSize}
          onPageIndexChange={setPageIndex}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPageIndex(0)
          }}
          hasExactCount={!query.isLoading}
          isTotalCountLoading={query.isLoading}
        />
      </AdminTableCard>
    </div>
  )
}

function ServerStatusBadge({ status }: { status?: ServerPublic["status"] }) {
  const labels = {
    enabled: "Enabled",
    invalid: "Invalid",
    disabled: "Disabled",
  } as const
  const value = status ?? "disabled"
  const classNames = {
    enabled:
      "border-green-200 bg-green-100 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-300",
    invalid:
      "border-red-200 bg-red-100 text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-300",
    disabled:
      "border-gray-200 bg-gray-100 text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300",
  } as const

  return <Badge className={classNames[value]}>{labels[value]}</Badge>
}

function ServerVisibilityBadge({ isPublic }: { isPublic: boolean }) {
  return isPublic ? (
    <Badge className="border-blue-200 bg-blue-100 text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300">
      Public
    </Badge>
  ) : (
    <Badge className="border-gray-200 bg-gray-100 text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
      Hidden
    </Badge>
  )
}

export function ServerGroupsTab({ canEditOwner }: { canEditOwner: boolean }) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [, copyToClipboard] = useCopyToClipboard()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "gokz-page-size-admin-server-groups",
  })
  const [sorting, setSorting] = useState<SortingState>([
    { id: "name", desc: false },
  ])
  const [editingGroup, setEditingGroup] =
    useState<AdminServerGroupPublic | null>(null)
  const [regeneratingGroup, setRegeneratingGroup] =
    useState<AdminServerGroupPublic | null>(null)
  const [creating, setCreating] = useState(false)
  const activeSort = sorting[0] ?? { id: "name", desc: false }
  const sortBy: ServerGroupSortBy =
    activeSort.id === "name" ||
    activeSort.id === "last_api_key_used_at" ||
    activeSort.id === "created_at" ||
    activeSort.id === "updated_at"
      ? activeSort.id
      : "name"
  const sortOrder = activeSort.desc ? "desc" : "asc"

  const query = useQuery({
    queryKey: [
      "admin-server-groups",
      "table",
      pageIndex,
      pageSize,
      sortBy,
      sortOrder,
    ],
    queryFn: () =>
      AdminServersService.readAdminServerGroups({
        offset: pageIndex * pageSize,
        limit: pageSize,
        sortBy,
        sortOrder,
      }),
    placeholderData: (previousData) => previousData,
  })
  const pageCount = Math.max(1, Math.ceil((query.data?.count ?? 0) / pageSize))

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    setSorting(next.length > 0 ? [next[0]] : [{ id: "name", desc: false }])
    setPageIndex(0)
  }

  useEffect(() => {
    setPageIndex((currentPageIndex) =>
      Math.min(currentPageIndex, pageCount - 1),
    )
  }, [pageCount])

  const handleCopyApiKey = useCallback(
    async (apiKey: string) => {
      const copied = await copyToClipboard(apiKey)
      if (copied) {
        showSuccessToast("Server group API key copied.")
      } else {
        showErrorToast("Clipboard is not available.")
      }
    },
    [copyToClipboard, showErrorToast, showSuccessToast],
  )

  const deleteMutation = useMutation({
    mutationFn: (groupId: string) =>
      AdminServersService.deleteAdminServerGroup({ groupId }),
    onSuccess: () => {
      showSuccessToast("Server group deleted.")
      void queryClient.invalidateQueries({ queryKey: ["admin-server-groups"] })
    },
    onError: (error: ApiError) => showErrorToast(extractErrorMessage(error)),
  })

  const rotateMutation = useMutation({
    mutationFn: (groupId: string) =>
      AdminServersService.rotateAdminServerGroupApiKey({ groupId }),
    onSuccess: () => {
      showSuccessToast("Server group API key regenerated.")
      setRegeneratingGroup(null)
      void queryClient.invalidateQueries({ queryKey: ["admin-server-groups"] })
    },
    onError: (error: ApiError) => showErrorToast(extractErrorMessage(error)),
  })

  const columns = useMemo<ColumnDef<AdminServerGroupPublic>[]>(
    () => [
      {
        accessorKey: "name",
        header: ({ column }) => (
          <SortableHeader column={column} label="Group" />
        ),
        cell: ({ row }) => (
          <div className="font-medium">{row.original.name}</div>
        ),
      },
      {
        accessorKey: "owner_steamid64",
        header: "Owner",
        cell: ({ row }) =>
          row.original.owner_steamid64 ? (
            <PlayerDisplay
              fallbackSteamid64={row.original.owner_steamid64}
              nameMaxLength={22}
            />
          ) : (
            <span className="text-muted-foreground">Unowned</span>
          ),
      },
      {
        accessorKey: "api_key",
        header: "API Key",
        cell: ({ row }) => {
          const apiKey = row.original.api_key
          const displayValue = `${apiKey.slice(0, 4)}****`

          return (
            <div className="flex max-w-80 items-center gap-2">
              <span className="min-w-0 flex-1 truncate font-mono text-xs">
                {displayValue}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Copy API key"
                onClick={() => void handleCopyApiKey(apiKey)}
              >
                <Copy />
              </Button>
            </div>
          )
        },
      },
      {
        accessorKey: "server_count",
        header: "Servers",
        cell: ({ row }) => row.original.server_count ?? 0,
      },
      {
        accessorKey: "last_api_key_used_at",
        header: ({ column }) => (
          <SortableHeader column={column} label="Last API Key Used" />
        ),
        cell: ({ row }) =>
          row.original.last_api_key_used_at ? (
            <FormattedDateTime value={row.original.last_api_key_used_at} />
          ) : (
            <span className="text-muted-foreground">Never</span>
          ),
      },
      {
        accessorKey: "created_at",
        header: ({ column }) => (
          <SortableHeader column={column} label="Created" />
        ),
        cell: ({ row }) => (
          <FormattedDateTime value={row.original.created_at} />
        ),
      },
      {
        accessorKey: "updated_at",
        header: ({ column }) => (
          <SortableHeader column={column} label="Updated" />
        ),
        cell: ({ row }) => (
          <FormattedDateTime value={row.original.updated_at} />
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Edit server group"
              onClick={() => setEditingGroup(row.original)}
            >
              <Pencil />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Regenerate API key"
              disabled={rotateMutation.isPending}
              onClick={() => setRegeneratingGroup(row.original)}
            >
              <RefreshCw />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="text-destructive hover:text-destructive"
              aria-label="Delete server group"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate(row.original.id)}
            >
              <Trash2 />
            </Button>
          </div>
        ),
      },
    ],
    [deleteMutation, handleCopyApiKey, rotateMutation],
  )

  return (
    <div className="flex flex-col gap-4">
      <AdminControlsCard>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <Button type="button" variant="outline" asChild>
            <a href={GOKZ_TOP_PLUGINS_URL} target="_blank" rel="noreferrer">
              <Github />
              Install gokz-top-plugins
            </a>
          </Button>
          <Button type="button" onClick={() => setCreating(true)}>
            <Plus />
            Create group
          </Button>
        </div>
      </AdminControlsCard>
      <AdminTableCard>
        <DataTable
          columns={columns}
          data={query.data?.data ?? []}
          isLoading={query.isLoading}
          stickyHeader
          stickyHeaderTopClassName="top-16"
          tableContainerClassName="md:overflow-visible"
          tableClassName="border-separate border-spacing-0"
          showFooter={false}
          disablePagination
          emptyText="No server groups found."
          sorting={{
            state: sorting,
            onSortingChange,
            manualSorting: true,
          }}
        />
        <TablePaginationFooter
          totalLabel="Groups"
          totalCount={query.data?.count ?? 0}
          pageIndex={pageIndex}
          pageCount={pageCount}
          pageSize={pageSize}
          onPageIndexChange={setPageIndex}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPageIndex(0)
          }}
          hasExactCount={!query.isLoading}
          isTotalCountLoading={query.isLoading}
        />
      </AdminTableCard>
      <ServerGroupDialog
        canEditOwner={canEditOwner}
        open={creating}
        onOpenChange={setCreating}
      />
      <ServerGroupDialog
        group={editingGroup}
        canEditOwner={canEditOwner}
        open={editingGroup !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditingGroup(null)
          }
        }}
      />
      <Dialog
        open={regeneratingGroup !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRegeneratingGroup(null)
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Regenerate API Key</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            The current API key for {regeneratingGroup?.name ?? "this group"}{" "}
            will stop working immediately.
          </p>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={rotateMutation.isPending}
              onClick={() => setRegeneratingGroup(null)}
            >
              Cancel
            </Button>
            <LoadingButton
              type="button"
              loading={rotateMutation.isPending}
              onClick={() => {
                if (regeneratingGroup) {
                  rotateMutation.mutate(regeneratingGroup.id)
                }
              }}
            >
              <KeyRound />
              Regenerate
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function ServerGroupDialog({
  group,
  canEditOwner,
  open,
  onOpenChange,
}: {
  group?: AdminServerGroupPublic | null
  canEditOwner: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [name, setName] = useState(group?.name ?? "")
  const [customId, setCustomId] = useState(group?.custom_id ?? "")
  const [website, setWebsite] = useState(group?.website ?? "")
  const [discord, setDiscord] = useState(group?.discord ?? "")
  const [steamGroup, setSteamGroup] = useState(group?.steam_group ?? "")
  const [owner, setOwner] = useState<PlayerDisplayPlayer | null>(
    group?.owner_steamid64 ? { steamid64: group.owner_steamid64 } : null,
  )

  useEffect(() => {
    if (!open) {
      return
    }
    setName(group?.name ?? "")
    setCustomId(group?.custom_id ?? "")
    setWebsite(group?.website ?? "")
    setDiscord(group?.discord ?? "")
    setSteamGroup(group?.steam_group ?? "")
    setOwner(
      group?.owner_steamid64 ? { steamid64: group.owner_steamid64 } : null,
    )
  }, [group, open])

  const mutation = useMutation({
    mutationFn: async () => {
      const trimmedCustomId = customId.trim()
      const requestBody = {
        name: name.trim(),
        custom_id: trimmedCustomId,
        website: website.trim() || null,
        discord: discord.trim() || null,
        steam_group: steamGroup.trim() || null,
        ...(group && canEditOwner
          ? { owner_steamid64: owner?.steamid64 ?? null }
          : {}),
      }
      if (group) {
        return await AdminServersService.updateAdminServerGroup({
          groupId: group.id,
          requestBody,
        })
      }
      return await AdminServersService.createAdminServerGroup({
        requestBody,
      })
    },
    onSuccess: () => {
      showSuccessToast(
        group ? "Server group updated." : "Server group created.",
      )
      onOpenChange(false)
      void queryClient.invalidateQueries({ queryKey: ["admin-server-groups"] })
    },
    onError: (error: ApiError) => showErrorToast(extractErrorMessage(error)),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {group ? "Edit Server Group" : "Create Server Group"}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <LabeledInput label="Name" value={name} onChange={setName} required />
          <LabeledInput
            label="Custom ID"
            value={customId}
            onChange={setCustomId}
            required
          />
          <LabeledInput label="Website" value={website} onChange={setWebsite} />
          <LabeledInput label="Discord" value={discord} onChange={setDiscord} />
          <LabeledInput
            label="Steam group"
            value={steamGroup}
            onChange={setSteamGroup}
          />
          {group ? (
            <PlayerSearchSelect
              id="server-group-owner"
              ariaLabel="Owner"
              label="Owner"
              placeholder="Search player ..."
              disabled={!canEditOwner || mutation.isPending}
              searchQueryKey={`server-group-owner-${group.id}`}
              selectedPlayer={owner}
              onSelectPlayer={setOwner}
              onClearPlayer={() => setOwner(null)}
            />
          ) : null}
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={mutation.isPending}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <LoadingButton
            type="button"
            loading={mutation.isPending}
            disabled={!name.trim()}
            onClick={() => mutation.mutate()}
          >
            <Save />
            {group ? "Save" : "Create"}
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function LabeledInput({
  label,
  value,
  onChange,
  required = false,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
}) {
  const id = useId()
  return (
    <div className="grid gap-2">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </label>
      <Input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}
