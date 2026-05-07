import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect, useBlocker } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { Check, ChevronDown, ChevronRight, Save } from "lucide-react"
import { useCallback, useDeferredValue, useMemo, useState } from "react"

import {
  type AdminMapPublic,
  AdminMapsService,
  type AdminRecordFilterPublic,
  UsersService,
} from "@/client"
import {
  AdminControlsCard,
  AdminPageHeader,
  AdminTableCard,
} from "@/components/Admin/AdminPageLayout"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { getScopeTone } from "@/components/Common/ScopeSelector"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import type { AppScope } from "@/components/scope-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { getPageTitle } from "@/lib/site"
import { canAccessAdminMaps } from "@/lib/user-roles"
import { cn } from "@/lib/utils"
import { handleError } from "@/utils"

type MapValidationDraft = {
  originalValidated: boolean
  validated: boolean
}
type MapValidationDrafts = Record<number, MapValidationDraft>
type FilterTierDraft = {
  mapId: number
  originalTier: number | null
  tier: number | null
}
type FilterTierDrafts = Record<number, FilterTierDraft>

function shouldIgnoreRowToggle(target: EventTarget | null) {
  if (!(target instanceof Element)) {
    return false
  }

  return Boolean(
    target.closest(
      'a, button, input, select, textarea, [role="button"], [role="checkbox"], [role="combobox"], [data-row-click-ignore="true"]',
    ),
  )
}

export const Route = createFileRoute("/_layout/admin/maps")({
  component: AdminMaps,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
    const user = await UsersService.readUserMe().catch(() => {
      localStorage.removeItem("access_token")
      throw redirect({
        to: "/login",
      })
    })
    if (!canAccessAdminMaps(user)) {
      throw redirect({
        to: "/",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: getPageTitle("Admin Maps"),
      },
    ],
  }),
})

function AdminMaps() {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [searchInput, setSearchInput] = useState("")
  const [validatedFilter, setValidatedFilter] = useState<
    "all" | "validated" | "unvalidated"
  >("all")
  const [expandedMapId, setExpandedMapId] = useState<string | null>(null)
  const [mapValidationDrafts, setMapValidationDrafts] =
    useState<MapValidationDrafts>({})
  const [filterTierDrafts, setFilterTierDrafts] = useState<FilterTierDrafts>({})
  const deferredSearchInput = useDeferredValue(searchInput)
  const normalizedSearch = deferredSearchInput.trim()
  const validated =
    validatedFilter === "all" ? undefined : validatedFilter === "validated"

  const mapsQueryKey = [
    "admin-maps",
    pageIndex,
    pageSize,
    normalizedSearch,
    validatedFilter,
  ]

  const { data, isLoading } = useQuery({
    queryFn: () =>
      AdminMapsService.readAdminMaps({
        offset: pageIndex * pageSize,
        limit: pageSize,
        q: normalizedSearch || undefined,
        validated,
      }),
    queryKey: mapsQueryKey,
  })

  const mapChanges = useMemo(
    () =>
      Object.entries(mapValidationDrafts).filter(
        ([, draft]) => draft.validated !== draft.originalValidated,
      ),
    [mapValidationDrafts],
  )
  const filterChanges = useMemo(
    () =>
      Object.entries(filterTierDrafts).filter(
        ([, draft]) => draft.tier !== draft.originalTier,
      ),
    [filterTierDrafts],
  )
  const hasUnsavedChanges = mapChanges.length > 0 || filterChanges.length > 0

  useBlocker({
    shouldBlockFn: () =>
      !window.confirm("You have unsaved changes. Leave this page anyway?"),
    enableBeforeUnload: hasUnsavedChanges,
    disabled: !hasUnsavedChanges,
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      await Promise.all([
        ...mapChanges.map(([id, draft]) =>
          AdminMapsService.updateAdminMap({
            id: Number(id),
            requestBody: { validated: draft.validated },
          }),
        ),
        ...filterChanges.map(([id, draft]) =>
          AdminMapsService.updateAdminRecordFilter({
            id: Number(id),
            requestBody: { tier: draft.tier },
          }),
        ),
      ])
    },
    onSuccess: () => {
      showSuccessToast("Admin map changes saved")
      setMapValidationDrafts({})
      setFilterTierDrafts({})
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-maps"] })
      void queryClient.invalidateQueries({
        queryKey: ["admin-map-record-filters"],
      })
    },
  })

  const setMapValidationDraft = useCallback(
    (map: AdminMapPublic, nextValidated: boolean) => {
      setMapValidationDrafts((current) => {
        const next = { ...current }
        if (nextValidated === map.validated) {
          delete next[map.id]
        } else {
          next[map.id] = {
            originalValidated: map.validated,
            validated: nextValidated,
          }
        }
        return next
      })
    },
    [],
  )

  const setFilterTierDraft = useCallback(
    (recordFilter: AdminRecordFilterPublic, nextTier: number | null) => {
      setFilterTierDrafts((current) => {
        const next = { ...current }
        if (nextTier === recordFilter.tier) {
          delete next[recordFilter.id]
        } else {
          next[recordFilter.id] = {
            mapId: recordFilter.map_id,
            originalTier: recordFilter.tier,
            tier: nextTier,
          }
        }
        return next
      })
    },
    [],
  )

  const columns = useMemo<ColumnDef<AdminMapPublic>[]>(
    () => [
      {
        accessorKey: "id",
        header: "ID",
        cell: ({ row }) => {
          const rowId = String(row.original.id)
          const isExpanded = expandedMapId === rowId

          return (
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`${isExpanded ? "Hide" : "Show"} record filters for ${row.original.name}`}
                className="shrink-0"
                data-row-click-ignore="true"
                onClick={() => setExpandedMapId(isExpanded ? null : rowId)}
              >
                {isExpanded ? <ChevronDown /> : <ChevronRight />}
              </Button>
              <span className="font-mono text-muted-foreground">
                {row.original.id}
              </span>
            </div>
          )
        },
      },
      {
        accessorKey: "name",
        header: "Map",
        cell: ({ row }) => (
          <MapDisplay mapName={row.original.name} className="min-w-0 w-64" />
        ),
      },
      {
        accessorKey: "tiers",
        header: "Tiers",
        cell: ({ row }) => <TierSummary map={row.original} />,
      },
      {
        accessorKey: "filesize",
        header: "Filesize",
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {formatBytes(row.original.filesize)}
          </span>
        ),
      },
      {
        accessorKey: "workshop_id",
        header: "Workshop",
        cell: ({ row }) =>
          row.original.workshop_id ? (
            <a
              className="text-primary underline-offset-4 hover:underline"
              href={`https://steamcommunity.com/sharedfiles/filedetails/?id=${row.original.workshop_id}`}
              rel="noreferrer"
              target="_blank"
            >
              {row.original.workshop_id}
            </a>
          ) : (
            <span className="text-muted-foreground">N/A</span>
          ),
      },
      {
        accessorKey: "created_on",
        header: "Created",
        cell: ({ row }) => (
          <FormattedDateTime
            className="text-muted-foreground"
            value={row.original.created_on}
            dateOnly
          />
        ),
      },
      {
        accessorKey: "updated_on",
        header: "Updated",
        cell: ({ row }) => (
          <FormattedDateTime
            className="text-muted-foreground"
            value={row.original.updated_on}
            dateOnly
          />
        ),
      },
      {
        accessorKey: "validated",
        header: "Validated",
        cell: ({ row }) => {
          const checked =
            mapValidationDrafts[row.original.id]?.validated ??
            row.original.validated
          return (
            <Switch
              aria-label={`Set ${row.original.name} validation`}
              checked={checked}
              disabled={saveMutation.isPending}
              onCheckedChange={(nextValidated) =>
                setMapValidationDraft(row.original, nextValidated)
              }
            />
          )
        },
      },
    ],
    [
      expandedMapId,
      mapValidationDrafts,
      saveMutation.isPending,
      setMapValidationDraft,
    ],
  )

  const tableData = data?.data ?? []
  const totalCount = data?.count ?? 0

  const toggleExpandedMap = useCallback((mapId: number) => {
    const rowId = String(mapId)
    setExpandedMapId((current) => (current === rowId ? null : rowId))
  }, [])

  return (
    <div className="flex flex-col gap-6">
      <AdminPageHeader title="Maps" />
      <AdminControlsCard>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <Input
            aria-label="Search maps"
            className="w-full sm:w-80"
            placeholder="Search maps..."
            value={searchInput}
            onChange={(event) => {
              setSearchInput(event.target.value)
              setPageIndex(0)
              setExpandedMapId(null)
            }}
          />
          <Select
            value={validatedFilter}
            onValueChange={(value) => {
              setValidatedFilter(value as "all" | "validated" | "unvalidated")
              setPageIndex(0)
              setExpandedMapId(null)
            }}
          >
            <SelectTrigger
              aria-label="Filter validation"
              className="w-full sm:w-44"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">All maps</SelectItem>
                <SelectItem value="validated">Validated</SelectItem>
                <SelectItem value="unvalidated">Unvalidated</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
          <LoadingButton
            type="button"
            loading={saveMutation.isPending}
            disabled={!hasUnsavedChanges}
            onClick={() => saveMutation.mutate()}
          >
            <Save data-icon="inline-start" />
            Save
          </LoadingButton>
        </div>
      </AdminControlsCard>

      <AdminTableCard>
        <DataTable
          columns={columns}
          data={tableData}
          stickyHeader
          stickyHeaderTopClassName="top-16"
          tableContainerClassName="md:overflow-visible"
          tableClassName="border-separate border-spacing-0"
          showFooter={false}
          emptyText="No maps found."
          getRowProps={(row) => ({
            "aria-expanded": expandedMapId === String(row.id),
            className: "cursor-pointer",
            onClick: (event) => {
              if (shouldIgnoreRowToggle(event.target)) {
                return
              }
              toggleExpandedMap(row.id)
            },
            onKeyDown: (event) => {
              if (event.target !== event.currentTarget) {
                return
              }
              if (event.key !== "Enter" && event.key !== " ") {
                return
              }
              event.preventDefault()
              toggleExpandedMap(row.id)
            },
            tabIndex: 0,
          })}
          getRowId={(row) => String(row.id)}
          expandedRowId={expandedMapId}
          renderExpandedContent={(map) => (
            <MapRecordFilters
              map={map}
              filterTierDrafts={filterTierDrafts}
              onTierDraftChange={setFilterTierDraft}
              disabled={saveMutation.isPending}
            />
          )}
          isLoading={isLoading}
          serverPagination={{
            pageIndex,
            pageSize,
            totalCount,
            onPageChange: (nextPageIndex) => {
              setPageIndex(nextPageIndex)
              setExpandedMapId(null)
            },
            onPageSizeChange: (nextPageSize) => {
              setPageSize(nextPageSize)
              setPageIndex(0)
              setExpandedMapId(null)
            },
          }}
        />
        <TablePaginationFooter
          totalLabel="Maps"
          totalCount={totalCount}
          pageIndex={pageIndex}
          pageCount={Math.max(1, Math.ceil(totalCount / pageSize))}
          pageSize={pageSize}
          onPageIndexChange={(nextPageIndex) => {
            setPageIndex(nextPageIndex)
            setExpandedMapId(null)
          }}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(nextPageSize)
            setPageIndex(0)
            setExpandedMapId(null)
          }}
          hasExactCount={!isLoading}
          isTotalCountLoading={isLoading}
        />
      </AdminTableCard>
    </div>
  )
}

function TierSummary({ map }: { map: AdminMapPublic }) {
  const tiers = [
    ["OVR", map.tiers.OVR],
    ["KZT", map.tiers.KZT],
    ["SKZ", map.tiers.SKZ],
    ["VNL", map.tiers.VNL],
  ] as const satisfies ReadonlyArray<readonly [AppScope, number | null]>

  return (
    <div className="flex flex-wrap gap-1.5">
      {tiers.map(([scope, tier]) => (
        <Badge
          key={scope}
          className={cn(
            "border-transparent font-mono font-semibold tracking-[0.16em]",
            getScopeTone(scope),
          )}
        >
          {scope} {tier ?? "N/A"}
        </Badge>
      ))}
    </div>
  )
}

function MapRecordFilters({
  map,
  filterTierDrafts,
  onTierDraftChange,
  disabled,
}: {
  map: AdminMapPublic
  filterTierDrafts: FilterTierDrafts
  onTierDraftChange: (
    recordFilter: AdminRecordFilterPublic,
    nextTier: number | null,
  ) => void
  disabled: boolean
}) {
  const { data, isLoading, isError } = useQuery({
    queryFn: () => AdminMapsService.readAdminMapRecordFilters({ id: map.id }),
    queryKey: ["admin-map-record-filters", map.id],
  })

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="text-sm text-muted-foreground">
        Failed to load record filters.
      </div>
    )
  }

  if (!data || data.stages.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        No 128-tick record filters for this map.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {data.stages.map((stage) => (
        <section key={stage.stage} className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">
            {stage.stage === 0 ? "Main stage" : `Stage ${stage.stage}`}
          </h2>
          <div className="overflow-hidden rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Filter</th>
                  <th className="px-3 py-2 text-left font-medium">Mode</th>
                  <th className="px-3 py-2 text-left font-medium">Type</th>
                  <th className="px-3 py-2 text-left font-medium">Tier</th>
                  <th className="px-3 py-2 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {stage.record_filters.map((recordFilter) => (
                  <RecordFilterTierRow
                    key={recordFilter.id}
                    recordFilter={recordFilter}
                    draftTier={filterTierDrafts[recordFilter.id]?.tier}
                    onTierDraftChange={onTierDraftChange}
                    disabled={disabled}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  )
}

function RecordFilterTierRow({
  recordFilter,
  draftTier,
  onTierDraftChange,
  disabled,
}: {
  recordFilter: AdminRecordFilterPublic
  draftTier: number | null | undefined
  onTierDraftChange: (
    recordFilter: AdminRecordFilterPublic,
    nextTier: number | null,
  ) => void
  disabled: boolean
}) {
  const selectedTier = draftTier ?? recordFilter.tier
  const isChanged = selectedTier !== recordFilter.tier

  return (
    <tr className="border-t">
      <td className="px-3 py-2 text-muted-foreground">#{recordFilter.id}</td>
      <td className="px-3 py-2">
        <ModeScopeBadge mode={recordFilter.mode} />
      </td>
      <td className="px-3 py-2">
        <RecordFilterTypeBadge hasTeleports={recordFilter.has_teleports} />
      </td>
      <td className="px-3 py-2">
        <TierSelector
          value={tierToSelectorValue(selectedTier)}
          onValueChange={(value) =>
            onTierDraftChange(
              recordFilter,
              value === "none" ? null : Number(value),
            )
          }
          includeAll={false}
          includeNone
          disabled={disabled}
          ariaLabel={`Tier for record filter ${recordFilter.id}`}
          triggerClassName="w-16 min-w-16 justify-center"
        />
      </td>
      <td className="px-3 py-2 text-right">
        {isChanged ? (
          <Badge variant="outline">Unsaved</Badge>
        ) : (
          <Check className="ml-auto text-muted-foreground" />
        )}
      </td>
    </tr>
  )
}

function ModeScopeBadge({ mode }: { mode: AdminRecordFilterPublic["mode"] }) {
  const scopeTone = getScopeTone(mode === "NKZ" ? "KZT" : (mode as AppScope))

  return (
    <Badge
      className={cn(
        "min-w-11 justify-center rounded-md border-transparent px-2 py-0.5 font-semibold tracking-[0.08em]",
        scopeTone,
      )}
    >
      {mode}
    </Badge>
  )
}

function RecordFilterTypeBadge({ hasTeleports }: { hasTeleports: boolean }) {
  return (
    <Badge
      className={cn(
        "w-12 border-transparent px-0 font-mono font-semibold tabular-nums",
        hasTeleports ? "text-slate-950" : "text-white",
      )}
      style={{
        backgroundColor: hasTeleports ? "#f2c40f" : "#3598db",
      }}
    >
      {hasTeleports ? "NUB" : "PRO"}
    </Badge>
  )
}

function tierToSelectorValue(tier: number | null): TierSelectorValue {
  return tier === null ? "none" : (String(tier) as `${number}`)
}

function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  const mib = bytes / 1024 / 1024
  if (mib >= 1) {
    return `${mib.toFixed(1)} MiB`
  }
  return `${(bytes / 1024).toFixed(1)} KiB`
}
