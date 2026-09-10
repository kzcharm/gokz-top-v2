import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect, useBlocker } from "@tanstack/react-router"
import {
  type ColumnDef,
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { ArrowDown, ArrowUp, ExternalLink, Plus, Save, X } from "lucide-react"
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
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { PlayerSearchSelect } from "@/components/Common/PlayerSearchSelect"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { ValidationStatusIconButton } from "@/components/Common/ValidationStatusIconButton"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"
import {
  fetchPlayersForDisplay,
  type GraphqlPlayer,
} from "@/lib/player-graphql"
import { getPageTitle } from "@/lib/site"
import { canAccessAdminMaps } from "@/lib/user-roles"
import { handleError } from "@/utils"

type MapValidationDraft = {
  originalValidated: boolean
  validated: boolean
}

type MapValidationDrafts = Record<number, MapValidationDraft>

type MapAuthorDraft = {
  authorsText: string
  noSteamidNamesText: string
}

type MapAuthorDrafts = Record<number, MapAuthorDraft>

type CourseTierDraft = {
  courseId: number
  mode: AdminCourseTierPublic["mode"]
  originalTier: number
  tier: number
}

type CourseTierDrafts = Record<string, CourseTierDraft>
type AdminMapSortBy = "id" | "name" | "filesize" | "created_at" | "updated_at"

function isAdminMapSortBy(value: string | undefined): value is AdminMapSortBy {
  return (
    value === "id" ||
    value === "name" ||
    value === "filesize" ||
    value === "created_at" ||
    value === "updated_at"
  )
}

function SortableHeader({
  title,
  column,
}: {
  title: string
  column: {
    getIsSorted: () => false | "asc" | "desc"
    toggleSorting: (desc?: boolean) => void
  }
}) {
  const sorting = column.getIsSorted()
  return (
    <Button
      type="button"
      variant="ghost"
      className="-ml-3 h-8 px-3"
      onClick={() => column.toggleSorting(sorting !== "desc")}
    >
      {title}
      {sorting === "asc" ? (
        <ArrowUp className="ml-2 size-4" />
      ) : sorting === "desc" ? (
        <ArrowDown className="ml-2 size-4" />
      ) : null}
    </Button>
  )
}

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

function formatAuthorText(values: string[] | null | undefined) {
  return (values ?? []).join("\n")
}

function parseAuthorText(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[\n,]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  )
}

function areStringListsEqual(left: string[], right: string[]) {
  if (left.length !== right.length) {
    return false
  }
  return left.every((value, index) => value === right[index])
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
    "validated" | "unvalidated"
  >("validated")
  const [sorting, setSorting] = useState<SortingState>([
    { id: "created_at", desc: true },
  ])
  const [editingMapId, setEditingMapId] = useState<number | null>(null)
  const [mapValidationDrafts, setMapValidationDrafts] =
    useState<MapValidationDrafts>({})
  const [mapAuthorDrafts, setMapAuthorDrafts] = useState<MapAuthorDrafts>({})
  const [courseTierDrafts, setCourseTierDrafts] = useState<CourseTierDrafts>({})
  const deferredSearchInput = useDeferredValue(searchInput)
  const normalizedSearch = deferredSearchInput.trim()
  const validated = validatedFilter === "validated"
  const activeSort = sorting[0] ?? { id: "created_at", desc: true }
  const sortBy = isAdminMapSortBy(activeSort.id) ? activeSort.id : "created_at"
  const sortOrder = activeSort.desc ? "desc" : "asc"

  const mapsQueryKey = [
    "admin-maps",
    pageIndex,
    pageSize,
    normalizedSearch,
    validatedFilter,
    sortBy,
    sortOrder,
  ]

  const { data, isLoading } = useQuery({
    queryFn: () =>
      AdminMapsService.readAdminMaps({
        offset: pageIndex * pageSize,
        limit: pageSize,
        q: normalizedSearch || undefined,
        validated,
        sortBy,
        sortOrder,
      }),
    queryKey: mapsQueryKey,
  })

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    const nextSort =
      next.length > 0 ? [next[0]] : [{ id: "created_at", desc: true }]
    setSorting(nextSort)
    setPageIndex(0)
    setEditingMapId(null)
  }

  const updateValidatedFilter = (
    nextValidatedFilter: "validated" | "unvalidated",
  ) => {
    setValidatedFilter(nextValidatedFilter)
    setPageIndex(0)
    setEditingMapId(null)
  }

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
  const mapAuthorChanges = useMemo(
    () =>
      Object.entries(mapAuthorDrafts)
        .map(([id, draft]) => {
          const map = data?.data.find(
            (candidate) => candidate.id === Number(id),
          )
          if (!map) {
            return null
          }
          const authors = parseAuthorText(draft.authorsText)
          const noSteamidNames = parseAuthorText(draft.noSteamidNamesText)
          if (
            areStringListsEqual(authors, map.authors ?? []) &&
            areStringListsEqual(noSteamidNames, map.no_steamid_names ?? [])
          ) {
            return null
          }
          return [id, { authors, noSteamidNames }] as const
        })
        .filter(
          (
            change,
          ): change is readonly [
            string,
            { authors: string[]; noSteamidNames: string[] },
          ] => change !== null,
        ),
    [data?.data, mapAuthorDrafts],
  )
  const hasUnsavedChanges =
    mapChanges.length > 0 ||
    mapAuthorChanges.length > 0 ||
    courseTierChanges.length > 0

  useBlocker({
    shouldBlockFn: () =>
      !window.confirm("You have unsaved changes. Leave this page anyway?"),
    enableBeforeUnload: hasUnsavedChanges,
    disabled: !hasUnsavedChanges,
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      const mapsById = new Map((data?.data ?? []).map((map) => [map.id, map]))
      const mapUpdatesById = new Map<
        number,
        {
          validated: boolean
          authors?: string[]
          no_steamid_names?: string[]
        }
      >()
      for (const [id, draft] of mapChanges) {
        const map = mapsById.get(Number(id))
        if (!map) {
          continue
        }
        mapUpdatesById.set(Number(id), {
          validated: draft.validated,
        })
      }
      for (const [id, authorDraft] of mapAuthorChanges) {
        const map = mapsById.get(Number(id))
        if (!map) {
          continue
        }
        const currentUpdate = mapUpdatesById.get(Number(id))
        mapUpdatesById.set(Number(id), {
          validated: currentUpdate?.validated ?? map.validated,
          authors: authorDraft.authors,
          no_steamid_names: authorDraft.noSteamidNames,
        })
      }
      await Promise.all([
        ...Array.from(mapUpdatesById.entries()).map(([id, requestBody]) =>
          AdminMapsService.updateAdminMap({
            id,
            requestBody,
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
      setMapAuthorDrafts({})
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

  const setMapAuthorDraft = useCallback(
    (map: AdminMapPublic, field: keyof MapAuthorDraft, nextValue: string) => {
      setMapAuthorDrafts((current) => {
        const existing = current[map.id] ?? {
          authorsText: formatAuthorText(map.authors),
          noSteamidNamesText: formatAuthorText(map.no_steamid_names),
        }
        const nextDraft = {
          ...existing,
          [field]: nextValue,
        }
        const nextAuthors = parseAuthorText(nextDraft.authorsText)
        const nextNoSteamidNames = parseAuthorText(nextDraft.noSteamidNamesText)
        const next = { ...current }
        if (
          areStringListsEqual(nextAuthors, map.authors ?? []) &&
          areStringListsEqual(nextNoSteamidNames, map.no_steamid_names ?? [])
        ) {
          delete next[map.id]
        } else {
          next[map.id] = nextDraft
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
        header: ({ column }) => <SortableHeader title="ID" column={column} />,
        size: 96,
        cell: ({ row }) => {
          return (
            <span className="font-mono text-muted-foreground">
              {row.original.id}
            </span>
          )
        },
      },
      {
        accessorKey: "name",
        header: ({ column }) => (
          <SortableHeader title="Map Name" column={column} />
        ),
        size: 300,
        cell: ({ row }) => (
          <MapDisplay
            mapName={row.original.name}
            mapId={row.original.id}
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
        enableSorting: false,
        size: 320,
        cell: ({ row }) => <TierSummary map={row.original} />,
      },
      {
        accessorKey: "filesize",
        header: ({ column }) => (
          <SortableHeader title="Filesize" column={column} />
        ),
        size: 120,
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {formatBytes(row.original.filesize)}
          </span>
        ),
      },
      {
        id: "created_at",
        accessorKey: "created_on",
        header: ({ column }) => (
          <SortableHeader title="Created" column={column} />
        ),
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
        id: "updated_at",
        accessorKey: "updated_on",
        header: ({ column }) => (
          <SortableHeader title="Updated" column={column} />
        ),
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
        enableSorting: false,
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
    [mapValidationDrafts, saveMutation.isPending, setMapValidationDraft],
  )

  const tableData = data?.data ?? []
  const totalCount = data?.count ?? 0
  const editingMap = tableData.find((map) => map.id === editingMapId) ?? null

  return (
    <div className="flex flex-col gap-6">
      <AdminPageHeader title="Maps" />
      <AdminControlsCard>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <Input
              aria-label="Search maps"
              className="w-full sm:w-80"
              placeholder="Search maps..."
              value={searchInput}
              onChange={(event) => {
                setSearchInput(event.target.value)
                setPageIndex(0)
                setEditingMapId(null)
              }}
            />
            <fieldset className="flex items-center">
              <legend className="sr-only">Filter validation</legend>
              <ValidationStatusIconButton
                status={
                  validatedFilter === "unvalidated" ? "invalid" : "validated"
                }
                label={
                  validatedFilter === "unvalidated"
                    ? "Show validated maps"
                    : "Show unvalidated maps"
                }
                pressed={validatedFilter === "unvalidated"}
                onClick={() =>
                  updateValidatedFilter(
                    validatedFilter === "unvalidated"
                      ? "validated"
                      : "unvalidated",
                  )
                }
              />
            </fieldset>
          </div>
          <LoadingButton
            type="button"
            className="sm:ml-auto"
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
            className: "cursor-pointer",
            onClick: (event) => {
              if (shouldIgnoreRowToggle(event.target)) {
                return
              }
              setEditingMapId(row.id)
            },
            onKeyDown: (event) => {
              if (event.target !== event.currentTarget) {
                return
              }
              if (event.key !== "Enter" && event.key !== " ") {
                return
              }
              event.preventDefault()
              setEditingMapId(row.id)
            },
            tabIndex: 0,
          })}
          getRowId={(row) => String(row.id)}
          isLoading={isLoading}
          sorting={{
            state: sorting,
            onSortingChange,
            manualSorting: true,
          }}
          serverPagination={{
            pageIndex,
            pageSize,
            totalCount,
            onPageChange: (nextPageIndex) => {
              setPageIndex(nextPageIndex)
              setEditingMapId(null)
            },
            onPageSizeChange: (nextPageSize) => {
              setPageSize(nextPageSize)
              setPageIndex(0)
              setEditingMapId(null)
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
            setEditingMapId(null)
          }}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(nextPageSize)
            setPageIndex(0)
            setEditingMapId(null)
          }}
          hasExactCount={!isLoading}
          isTotalCountLoading={isLoading}
        />
      </AdminTableCard>
      <Dialog
        open={editingMap !== null}
        onOpenChange={(open) => {
          if (!open) setEditingMapId(null)
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          {editingMap ? (
            <>
              <DialogHeader>
                <DialogTitle>Edit {editingMap.name}</DialogTitle>
                <DialogDescription>
                  Update authors and course tiers, then save your changes.
                </DialogDescription>
              </DialogHeader>
              <MapDetailsPanel
                map={editingMap}
                authorDraft={mapAuthorDrafts[editingMap.id]}
                courseTierDrafts={courseTierDrafts}
                onAuthorDraftChange={setMapAuthorDraft}
                onCourseTierDraftChange={setCourseTierDraft}
                disabled={saveMutation.isPending}
              />
            </>
          ) : null}
        </DialogContent>
      </Dialog>
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
  authorDraft,
  courseTierDrafts,
  onAuthorDraftChange,
  onCourseTierDraftChange,
  disabled,
}: {
  map: AdminMapPublic
  authorDraft?: MapAuthorDraft
  courseTierDrafts: CourseTierDrafts
  onAuthorDraftChange: (
    map: AdminMapPublic,
    field: keyof MapAuthorDraft,
    nextValue: string,
  ) => void
  onCourseTierDraftChange: (
    courseTier: AdminCourseTierPublic,
    nextTier: number,
  ) => void
  disabled: boolean
}) {
  return (
    <div className="space-y-6 rounded-[24px] border border-border/70 bg-gradient-to-br from-card via-card to-muted/20 p-5 shadow-sm">
      <MapAuthorEditor
        map={map}
        authorDraft={authorDraft}
        onAuthorDraftChange={onAuthorDraftChange}
        disabled={disabled}
      />
      <MapCourseTierEditor
        map={map}
        courseTierDrafts={courseTierDrafts}
        onCourseTierDraftChange={onCourseTierDraftChange}
        disabled={disabled}
      />
    </div>
  )
}

function MapAuthorEditor({
  map,
  authorDraft,
  onAuthorDraftChange,
  disabled,
}: {
  map: AdminMapPublic
  authorDraft?: MapAuthorDraft
  onAuthorDraftChange: (
    map: AdminMapPublic,
    field: keyof MapAuthorDraft,
    nextValue: string,
  ) => void
  disabled: boolean
}) {
  const authorsText = authorDraft?.authorsText ?? formatAuthorText(map.authors)
  const noSteamidNamesText =
    authorDraft?.noSteamidNamesText ?? formatAuthorText(map.no_steamid_names)
  const steamidAuthors = parseAuthorText(authorsText)
  const [isAddingAuthor, setIsAddingAuthor] = useState(false)
  const [selectedAuthor, setSelectedAuthor] = useState<GraphqlPlayer | null>(
    null,
  )
  const { data: players = [], isLoading: isLoadingPlayers } = useQuery({
    queryKey: ["admin-map-authors", steamidAuthors],
    queryFn: () => fetchPlayersForDisplay(steamidAuthors),
    enabled: steamidAuthors.length > 0,
    staleTime: 60_000,
  })
  const playersBySteamid = useMemo(
    () => new Map(players.map((player) => [player?.steamid64, player])),
    [players],
  )

  const updateSteamidAuthors = (nextAuthors: string[]) => {
    onAuthorDraftChange(map, "authorsText", nextAuthors.join("\n"))
  }

  const addAuthor = () => {
    if (!selectedAuthor || steamidAuthors.includes(selectedAuthor.steamid64)) {
      return
    }
    updateSteamidAuthors([...steamidAuthors, selectedAuthor.steamid64])
    setSelectedAuthor(null)
    setIsAddingAuthor(false)
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold">Authors</h2>
      </div>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-medium">SteamID64 Authors</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={disabled}
              data-row-click-ignore="true"
              onClick={() => {
                setSelectedAuthor(null)
                setIsAddingAuthor((current) => !current)
              }}
            >
              <Plus data-icon="inline-start" />
              Add author
            </Button>
          </div>
          <div className="flex flex-col divide-y rounded-md border border-border/70 bg-background">
            {steamidAuthors.length === 0 ? (
              <p className="px-3 py-3 text-sm text-muted-foreground">
                No SteamID64 authors added.
              </p>
            ) : (
              steamidAuthors.map((steamid64) => {
                const player = playersBySteamid.get(steamid64)
                return (
                  <div
                    key={steamid64}
                    className="flex min-h-12 items-center justify-between gap-3 px-3 py-2"
                  >
                    <PlayerDisplay
                      player={player ?? { steamid64 }}
                      fallbackSteamid64={steamid64}
                      className="min-w-0"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Remove author ${steamid64}`}
                      disabled={disabled}
                      data-row-click-ignore="true"
                      onClick={() =>
                        updateSteamidAuthors(
                          steamidAuthors.filter((value) => value !== steamid64),
                        )
                      }
                    >
                      <X />
                    </Button>
                  </div>
                )
              })
            )}
          </div>
          {isLoadingPlayers && steamidAuthors.length > 0 ? (
            <span className="text-xs text-muted-foreground">
              Loading player details...
            </span>
          ) : null}
          {isAddingAuthor ? (
            <div className="flex items-end gap-2" data-row-click-ignore="true">
              <div className="min-w-0 flex-1">
                <PlayerSearchSelect
                  ariaLabel="Search author"
                  placeholder="Search player to add..."
                  selectedPlayer={selectedAuthor}
                  onClearPlayer={() => setSelectedAuthor(null)}
                  onSelectPlayer={setSelectedAuthor}
                  searchQueryKey={`admin-map-author-${map.id}`}
                />
              </div>
              <Button
                type="button"
                size="sm"
                disabled={
                  !selectedAuthor ||
                  disabled ||
                  steamidAuthors.includes(selectedAuthor.steamid64)
                }
                onClick={addAuthor}
              >
                Add
              </Button>
            </div>
          ) : null}
        </div>
        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium">Name-Only Authors</span>
          <textarea
            className="min-h-28 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            value={noSteamidNamesText}
            disabled={disabled}
            data-row-click-ignore="true"
            onChange={(event) =>
              onAuthorDraftChange(map, "noSteamidNamesText", event.target.value)
            }
          />
        </label>
      </div>
    </section>
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
