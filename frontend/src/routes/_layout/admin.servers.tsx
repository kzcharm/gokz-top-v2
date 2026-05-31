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
  Copy,
  Github,
  KeyRound,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react"
import { useCallback, useEffect, useId, useMemo, useState } from "react"

import {
  type AdminServerAccessPublic,
  type AdminServerGroupPublic,
  AdminServersService,
  type ApiError,
  type ServerGlobalapiAdminPublic,
  type ServerPublic,
  UsersService,
} from "@/client"
import {
  AdminControlsCard,
  AdminPageHeader,
  AdminTableCard,
} from "@/components/Admin/AdminPageLayout"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { isLoggedIn } from "@/hooks/useAuth"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import useCustomToast from "@/hooks/useCustomToast"
import { getPageTitle } from "@/lib/site"
import { isSuperuser } from "@/lib/user-roles"
import { extractErrorMessage } from "@/utils"

const NO_GROUP = "__none"
const GOKZ_TOP_PLUGINS_URL = "https://github.com/kzcharm/gokz-top-plugins"
type GlobalApiSortBy = "id" | "server" | "updated_at" | "created_at"

const ADMIN_SERVER_TAB_OPTIONS = [
  {
    value: "globalapi",
    label: "GlobalAPI Server",
    to: "/admin/servers/globalapi-server",
  },
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
  const accessQuery = useQuery({
    queryKey: ["admin-servers-access"],
    queryFn: () => AdminServersService.readAdminServerAccess(),
  })
  const groupsQuery = useQuery({
    queryKey: ["admin-server-groups"],
    queryFn: () => AdminServersService.readAdminServerGroups(),
  })

  const access = accessQuery.data
  const groups = groupsQuery.data?.data ?? []
  const activeTab =
    ADMIN_SERVER_TAB_OPTIONS.find((tab) => pathname.startsWith(tab.to))
      ?.value ?? "globalapi"

  return (
    <div className="flex flex-col gap-6">
      <AdminPageHeader
        title="Servers"
        aside={access ? <RoleBadge access={access} /> : null}
      />

      <Tabs value={activeTab} className="gap-5">
        <TabsList className="w-full justify-start overflow-x-auto sm:w-fit">
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
        {activeTab === "groups" ? <ServerGroupsTab groups={groups} /> : null}
      </Tabs>
    </div>
  )
}

function RoleBadge({ access }: { access: AdminServerAccessPublic }) {
  return (
    <Badge variant={access.role === "root_admin" ? "default" : "secondary"}>
      {access.role === "root_admin" ? "Root Admin" : "Server Owner"}
    </Badge>
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
  const [pageSize, setPageSize] = useState(20)
  const [search, setSearch] = useState("")
  const [approvalFilter, setApprovalFilter] = useState("1")
  const [sorting, setSorting] = useState<SortingState>([
    { id: "id", desc: true },
  ])
  const canApprove = access?.can_approve_servers ?? false
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
      approvalStatus,
    }: {
      serverId: number
      groupId?: string | null
      approvalStatus?: number
    }) =>
      AdminServersService.updateAdminGlobalapiServer({
        serverId,
        requestBody: {
          ...(groupId !== undefined ? { group_id: groupId } : {}),
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

  const columns = useMemo<ColumnDef<ServerGlobalapiAdminPublic>[]>(
    () => [
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
            <div className="font-mono text-xs text-muted-foreground">
              {row.original.ip || "unknown"}:{row.original.port}
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
          <Select
            value={row.original.group_id ?? NO_GROUP}
            disabled={groupsLoading || updateMutation.isPending}
            onValueChange={(value) =>
              updateMutation.mutate({
                serverId: row.original.id,
                groupId: value === NO_GROUP ? null : value,
              })
            }
          >
            <SelectTrigger className="w-52">
              <SelectValue placeholder="No group" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_GROUP}>No group</SelectItem>
              {groups.map((group) => (
                <SelectItem key={group.id} value={group.id}>
                  {group.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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
        header: "Approved",
        cell: ({ row }) =>
          canApprove ? (
            <Switch
              checked={row.original.approval_status === 1}
              disabled={updateMutation.isPending}
              onCheckedChange={(checked) =>
                updateMutation.mutate({
                  serverId: row.original.id,
                  approvalStatus: checked ? 1 : 0,
                })
              }
            />
          ) : (
            <Badge
              variant={
                row.original.approval_status === 1 ? "default" : "secondary"
              }
            >
              {row.original.approval_status === 1 ? "Approved" : "Pending"}
            </Badge>
          ),
      },
    ],
    [canApprove, groups, groupsLoading, updateMutation],
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
    </div>
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
  const [pageSize, setPageSize] = useState(20)
  const [groupFilter, setGroupFilter] = useState("all")
  const canClearGroup = access?.role !== "server_owner"

  const query = useQuery({
    queryKey: ["admin-public-servers", pageIndex, pageSize, groupFilter],
    queryFn: () =>
      AdminServersService.readAdminPublicServers({
        offset: pageIndex * pageSize,
        limit: pageSize,
        groupId: groupFilter === "all" ? undefined : groupFilter,
      }),
  })

  const updateMutation = useMutation({
    mutationFn: ({
      serverId,
      groupId,
      status,
    }: {
      serverId: string
      groupId?: string | null
      status?: ServerPublic["status"]
    }) =>
      AdminServersService.updateAdminPublicServer({
        serverId,
        requestBody: {
          ...(groupId !== undefined ? { group_id: groupId } : {}),
          ...(status !== undefined ? { status } : {}),
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
        accessorKey: "ip",
        header: "Server",
        cell: ({ row }) => (
          <div>
            <div className="font-mono text-sm">
              {row.original.ip}:{row.original.port}
            </div>
            <div className="text-xs text-muted-foreground">
              {row.original.live_status?.hostname || "No live hostname"}
            </div>
          </div>
        ),
      },
      {
        accessorKey: "group_id",
        header: "Group",
        cell: ({ row }) => (
          <Select
            value={row.original.group_id ?? NO_GROUP}
            disabled={updateMutation.isPending}
            onValueChange={(value) =>
              updateMutation.mutate({
                serverId: row.original.id,
                groupId: value === NO_GROUP ? null : value,
              })
            }
          >
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
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <Select
            value={row.original.status}
            disabled={updateMutation.isPending}
            onValueChange={(value) =>
              updateMutation.mutate({
                serverId: row.original.id,
                status: value as ServerPublic["status"],
              })
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
        ),
      },
      {
        accessorKey: "country",
        header: "Location",
        cell: ({ row }) => (
          <span className="text-sm text-muted-foreground">
            {[row.original.country, row.original.city]
              .filter(Boolean)
              .join(", ") || "Unknown"}
          </span>
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
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
        ),
      },
    ],
    [canClearGroup, deleteMutation, groups, updateMutation],
  )

  return (
    <div className="flex flex-col gap-4">
      <AdminControlsCard>
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
            {groups.map((group) => (
              <SelectItem key={group.id} value={group.id}>
                {group.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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

export function ServerGroupsTab({
  groups,
}: {
  groups: AdminServerGroupPublic[]
}) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [, copyToClipboard] = useCopyToClipboard()
  const [editingGroup, setEditingGroup] =
    useState<AdminServerGroupPublic | null>(null)
  const [regeneratingGroup, setRegeneratingGroup] =
    useState<AdminServerGroupPublic | null>(null)
  const [creating, setCreating] = useState(false)

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
        header: "Group",
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
        header: "Last API Key Used",
        cell: ({ row }) =>
          row.original.last_api_key_used_at ? (
            <FormattedDateTime value={row.original.last_api_key_used_at} />
          ) : (
            <span className="text-muted-foreground">Never</span>
          ),
      },
      {
        accessorKey: "created_at",
        header: "Created",
        cell: ({ row }) => (
          <FormattedDateTime value={row.original.created_at} />
        ),
      },
      {
        accessorKey: "updated_at",
        header: "Updated",
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
          data={groups}
          stickyHeader
          stickyHeaderTopClassName="top-16"
          tableContainerClassName="md:overflow-visible"
          tableClassName="border-separate border-spacing-0"
          showFooter={false}
          emptyText="No server groups found."
        />
      </AdminTableCard>
      <ServerGroupDialog open={creating} onOpenChange={setCreating} />
      <ServerGroupDialog
        group={editingGroup}
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
  open,
  onOpenChange,
}: {
  group?: AdminServerGroupPublic | null
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

  useEffect(() => {
    if (!open) {
      return
    }
    setName(group?.name ?? "")
    setCustomId(group?.custom_id ?? "")
    setWebsite(group?.website ?? "")
    setDiscord(group?.discord ?? "")
    setSteamGroup(group?.steam_group ?? "")
  }, [group, open])

  const mutation = useMutation({
    mutationFn: async () => {
      const requestBody = {
        name: name.trim(),
        custom_id: customId.trim() || null,
        website: website.trim() || null,
        discord: discord.trim() || null,
        steam_group: steamGroup.trim() || null,
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
          />
          <LabeledInput label="Website" value={website} onChange={setWebsite} />
          <LabeledInput label="Discord" value={discord} onChange={setDiscord} />
          <LabeledInput
            label="Steam group"
            value={steamGroup}
            onChange={setSteamGroup}
          />
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
