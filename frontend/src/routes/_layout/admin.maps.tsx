import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect, useBlocker } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { ChevronDown, ChevronRight, ExternalLink, Save } from "lucide-react"
import {
  Fragment,
  useCallback,
  useDeferredValue,
  useMemo,
  useState,
} from "react"

import {
  type AdminCourseTierPublic,
  type AdminMapPublic,
  AdminMapsService,
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
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
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
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"
import { getPageTitle } from "@/lib/site"
import { canAccessAdminMaps } from "@/lib/user-roles"
import { handleError } from "@/utils"

type MapValidationDraft = {
  originalValidated: boolean
  validated: boolean
}

type MapValidationDrafts = Record<number, MapValidationDraft>

type CourseTierDraft = {
  courseId: number
  mode: AdminCourseTierPublic["mode"]
  originalTier: number
  tier: number
}

type CourseTierDrafts = Record<string, CourseTierDraft>

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

function courseTierDraftKey(
  courseId: number,
  mode: AdminCourseTierPublic["mode"],
) {
  return `${courseId}:${mode}`
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
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "gokz-page-size-admin-maps",
  })
  const [searchInput, setSearchInput] = useState("")
  const [validatedFilter, setValidatedFilter] = useState<
    "all" | "validated" | "unvalidated"
  >("all")
  const [expandedMapId, setExpandedMapId] = useState<string | null>(null)
  const [mapValidationDrafts, setMapValidationDrafts] =
    useState<MapValidationDrafts>({})
  const [courseTierDrafts, setCourseTierDrafts] = useState<CourseTierDrafts>({})
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
  const courseTierChanges = useMemo(
    () =>
      Object.entries(courseTierDrafts).filter(
        ([, draft]) => draft.tier !== draft.originalTier,
      ),
    [courseTierDrafts],
  )
  const hasUnsavedChanges =
    mapChanges.length > 0 || courseTierChanges.length > 0

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
        ...courseTierChanges.map(([, draft]) =>
          AdminMapsService.updateAdminCourseTier({
            courseId: draft.courseId,
            mode: draft.mode,
            requestBody: { tier: draft.tier },
          }),
        ),
      ])
    },
    onSuccess: () => {
      showSuccessToast("Admin map changes saved")
      setMapValidationDrafts({})
      setCourseTierDrafts({})
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-maps"] })
      void queryClient.invalidateQueries({
        queryKey: ["admin-map-course-tiers"],
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

  const setCourseTierDraft = useCallback(
    (courseTier: AdminCourseTierPublic, nextTier: number) => {
      const key = courseTierDraftKey(courseTier.course_id, courseTier.mode)
      setCourseTierDrafts((current) => {
        const next = { ...current }
        if (nextTier === courseTier.tier) {
          delete next[key]
        } else {
          next[key] = {
            courseId: courseTier.course_id,
            mode: courseTier.mode,
            originalTier: courseTier.tier,
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
        size: 96,
        cell: ({ row }) => {
          const rowId = String(row.original.id)
          const isExpanded = expandedMapId === rowId

          return (
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`${isExpanded ? "Hide" : "Show"} course tiers for ${row.original.name}`}
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
        size: 300,
        cell: ({ row }) => (
          <MapDisplay
            mapName={row.original.name}
            className="min-w-0 w-64"
            contextMenuItems={
              row.original.workshop_id ? (
                <DropdownMenuItem
                  onSelect={(event) => {
                    event.preventDefault()
                    window.open(
                      `https://steamcommunity.com/sharedfiles/filedetails/?id=${row.original.workshop_id}`,
                      "_blank",
                      "noopener,noreferrer",
                    )
                  }}
                >
                  <ExternalLink />
                  Open Workshop
                </DropdownMenuItem>
              ) : null
            }
          />
        ),
      },
      {
        accessorKey: "tiers",
        header: "Tiers",
        size: 320,
        cell: ({ row }) => <TierSummary map={row.original} />,
      },
      {
        accessorKey: "filesize",
        header: "Filesize",
        size: 120,
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {formatBytes(row.original.filesize)}
          </span>
        ),
      },
      {
        accessorKey: "created_on",
        header: "Created",
        size: 120,
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
        size: 120,
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
        size: 120,
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
          tableClassName="table-fixed border-separate border-spacing-0"
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
            <MapDetailsPanel
              map={map}
              courseTierDrafts={courseTierDrafts}
              onCourseTierDraftChange={setCourseTierDraft}
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
    ["KZT", map.tiers.KZT ?? 0],
    ["SKZ", map.tiers.SKZ ?? 0],
    ["VNL", map.tiers.VNL ?? 0],
  ] as const

  return (
    <div className="flex items-center gap-2 whitespace-nowrap">
      {tiers.map(([scope, tier], index) => (
        <Fragment key={scope}>
          {index > 0 ? <span className="text-muted-foreground">|</span> : null}
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium">{scope}</span>
            <TierBadge
              tier={tier}
              className="px-2 py-0.5"
              hideWhenUnknown={false}
            />
          </div>
        </Fragment>
      ))}
    </div>
  )
}

function MapDetailsPanel({
  map,
  courseTierDrafts,
  onCourseTierDraftChange,
  disabled,
}: {
  map: AdminMapPublic
  courseTierDrafts: CourseTierDrafts
  onCourseTierDraftChange: (
    courseTier: AdminCourseTierPublic,
    nextTier: number,
  ) => void
  disabled: boolean
}) {
  return (
    <div className="rounded-[24px] border border-border/70 bg-gradient-to-br from-card via-card to-muted/20 p-5 shadow-sm">
      <MapCourseTierEditor
        map={map}
        courseTierDrafts={courseTierDrafts}
        onCourseTierDraftChange={onCourseTierDraftChange}
        disabled={disabled}
      />
    </div>
  )
}

function MapCourseTierEditor({
  map,
  courseTierDrafts,
  onCourseTierDraftChange,
  disabled,
}: {
  map: AdminMapPublic
  courseTierDrafts: CourseTierDrafts
  onCourseTierDraftChange: (
    courseTier: AdminCourseTierPublic,
    nextTier: number,
  ) => void
  disabled: boolean
}) {
  const { data, isLoading, isError } = useQuery({
    queryFn: () => AdminMapsService.readAdminMapCourseTiers({ id: map.id }),
    queryKey: ["admin-map-course-tiers", map.id],
  })

  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-semibold">Course tiers</h2>
        </div>
        {data && data.stages.length > 0 ? (
          <Badge variant="outline" className="w-fit text-[11px] uppercase">
            {data.stages.length}{" "}
            {data.stages.length === 1 ? "course" : "courses"}
          </Badge>
        ) : null}
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : null}

      {isError ? (
        <div className="text-sm text-muted-foreground">
          Failed to load course tiers.
        </div>
      ) : null}

      {!isLoading && !isError && (!data || data.stages.length === 0) ? (
        <div className="text-sm text-muted-foreground">
          No exact 128-tick courses are available for this map yet.
        </div>
      ) : null}

      {!isLoading && !isError && data && data.stages.length > 0 ? (
        <div className="overflow-hidden rounded-2xl border border-border/70 bg-background/80 shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-muted/35 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Stage</th>
                <th className="px-4 py-3 text-center font-medium">KZT</th>
                <th className="px-4 py-3 text-center font-medium">SKZ</th>
                <th className="px-4 py-3 text-center font-medium">VNL</th>
              </tr>
            </thead>
            <tbody>
              {data.stages.map((stage) => (
                <CourseTierStageRow
                  key={stage.course_id}
                  stage={stage}
                  courseTierDrafts={courseTierDrafts}
                  onCourseTierDraftChange={onCourseTierDraftChange}
                  disabled={disabled}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}

function CourseTierStageRow({
  stage,
  courseTierDrafts,
  onCourseTierDraftChange,
  disabled,
}: {
  stage: {
    stage: number
    course_id: number
    course_tiers: Array<AdminCourseTierPublic>
  }
  courseTierDrafts: CourseTierDrafts
  onCourseTierDraftChange: (
    courseTier: AdminCourseTierPublic,
    nextTier: number,
  ) => void
  disabled: boolean
}) {
  const visibleModes = stage.course_tiers.filter(
    (courseTier) => courseTier.mode !== "NKZ",
  )
  const draftAwareCourseTiers = visibleModes.map((courseTier) => {
    const draft =
      courseTierDrafts[
        courseTierDraftKey(courseTier.course_id, courseTier.mode)
      ]
    return {
      courseTier,
      selectedTier: draft?.tier ?? courseTier.tier,
    }
  })
  const isChanged = draftAwareCourseTiers.some(
    ({ courseTier, selectedTier }) => selectedTier !== courseTier.tier,
  )

  return (
    <tr className="border-t border-border/60">
      <td className="px-4 py-3 font-medium">
        <div className="flex items-center gap-3">
          <span>
            {stage.stage === 0 ? "Main stage" : `Stage ${stage.stage}`}
          </span>
          {isChanged ? (
            <Badge variant="outline" className="text-[11px]">
              Draft
            </Badge>
          ) : null}
        </div>
      </td>
      {draftAwareCourseTiers.map(({ courseTier, selectedTier }) => (
        <td key={courseTier.mode} className="px-4 py-3 text-center">
          <TierSelector
            value={tierToSelectorValue(selectedTier)}
            onValueChange={(value) =>
              onCourseTierDraftChange(
                courseTier,
                value === "none" ? 0 : Number(value),
              )
            }
            includeAll={false}
            includeNone
            noneLabel="T0"
            disabled={disabled}
            ariaLabel={`Tier for ${courseTier.mode} on course ${courseTier.course_id}`}
            triggerClassName="mx-auto w-18 min-w-18 justify-center"
          />
        </td>
      ))}
    </tr>
  )
}

function tierToSelectorValue(tier: number): TierSelectorValue {
  return tier === 0 ? "none" : (String(tier) as `${number}`)
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
