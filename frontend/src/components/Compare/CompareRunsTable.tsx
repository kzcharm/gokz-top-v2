import type { ColumnDef } from "@tanstack/react-table"
import { ArrowDown, ArrowUp } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import type { PlayerCompareRunPublic, RecordPublic } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapDisplay } from "@/components/Common/MapDisplay"
import {
  ModeSelector,
  type ModeSelectorValue,
} from "@/components/Common/ModeSelector"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { ModeBadge } from "@/components/Records/ModeBadge"
import { PointsBadge } from "@/components/Records/PointsBadge"
import { TeleportsBadge } from "@/components/Records/TeleportsBadge"
import { formatRecordTime } from "@/components/Records/utils"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"
import { cn } from "@/lib/utils"

type SortKey =
  | "map"
  | "tier"
  | "time_delta"
  | "points_delta"
  | `${"player1" | "player2"}.${"mode" | "teleports" | "time" | "points" | "created_on"}`
const EMPTY_FILTERS = {
  map: "",
  server: "",
  mode: "all" as ModeSelectorValue,
  tier: "all" as TierSelectorValue,
  target: "either",
  minTime: "",
  maxTime: "",
  minPoints: "",
  maxPoints: "",
  minTeleports: "",
  maxTeleports: "",
  fromDate: "",
  toDate: "",
}

function valueFor(
  row: PlayerCompareRunPublic,
  key: SortKey,
): string | number | null {
  if (key === "map") return row.map_name
  if (key === "tier") return row.map_tier
  if (key === "time_delta" || key === "points_delta") return row[key] ?? null
  const [player, field] = key.split(".") as [
    "player1" | "player2",
    "mode" | "teleports" | "time" | "points" | "created_on",
  ]
  if (field === "created_on") {
    const timestamp = Date.parse(row[player]?.created_on ?? "")
    return Number.isFinite(timestamp) ? timestamp : null
  }
  return row[player]?.[field] ?? null
}

export function CompareRunsTable({
  rows,
  player1Name,
  player2Name,
  onlyBoth,
}: {
  rows: PlayerCompareRunPublic[]
  player1Name: string
  player2Name: string
  onlyBoth: boolean
}) {
  const { t } = useTranslation()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({
    key: "player1.created_on",
    desc: true,
  })
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "compare-runs-page-size",
    defaultPageSize: 50,
  })
  const update = <K extends keyof typeof filters>(
    key: K,
    value: (typeof filters)[K],
  ) => {
    setFilters((current) => ({ ...current, [key]: value }))
    setPageIndex(0)
  }
  const filteredRows = useMemo(() => {
    const bounded = (value: number, min: string, max: string) =>
      (!min || value >= Number(min)) && (!max || value <= Number(max))
    const hasRunFilters =
      filters.mode !== "all" ||
      filters.server.trim() ||
      filters.minTime ||
      filters.maxTime ||
      filters.minPoints ||
      filters.maxPoints ||
      filters.minTeleports ||
      filters.maxTeleports ||
      filters.fromDate ||
      filters.toDate
    const matches = (record: RecordPublic | null | undefined) =>
      Boolean(
        record &&
          (filters.mode === "all" ||
            record.mode.toUpperCase() === filters.mode) &&
          (!filters.server.trim() ||
            record.server_name
              ?.toLowerCase()
              .includes(filters.server.trim().toLowerCase())) &&
          bounded(record.time, filters.minTime, filters.maxTime) &&
          bounded(record.points, filters.minPoints, filters.maxPoints) &&
          bounded(
            record.teleports,
            filters.minTeleports,
            filters.maxTeleports,
          ) &&
          (!filters.fromDate ||
            new Date(record.created_on).getTime() >=
              new Date(`${filters.fromDate}T00:00:00`).getTime()) &&
          (!filters.toDate ||
            new Date(record.created_on).getTime() <=
              new Date(`${filters.toDate}T23:59:59.999`).getTime()),
      )
    return rows
      .filter((row) => {
        if (onlyBoth && (!row.player1 || !row.player2)) return false
        if (
          !row.map_name.toLowerCase().includes(filters.map.trim().toLowerCase())
        )
          return false
        if (
          filters.tier !== "all" &&
          row.map_tier !== (filters.tier === "none" ? 0 : Number(filters.tier))
        )
          return false
        if (!hasRunFilters) return true
        if (filters.target === "player1") return matches(row.player1)
        if (filters.target === "player2") return matches(row.player2)
        return filters.target === "both"
          ? matches(row.player1) && matches(row.player2)
          : matches(row.player1) || matches(row.player2)
      })
      .sort((a, b) => {
        const left = valueFor(a, sort.key),
          right = valueFor(b, sort.key)
        if (left == null || right == null)
          return left == null && right == null
            ? a.map_name.localeCompare(b.map_name)
            : left == null
              ? 1
              : -1
        const result =
          typeof left === "number" && typeof right === "number"
            ? left - right
            : String(left).localeCompare(String(right), undefined, {
                numeric: true,
                sensitivity: "base",
              })
        return (
          (sort.desc ? -result : result) || a.map_name.localeCompare(b.map_name)
        )
      })
  }, [rows, filters, sort, onlyBoth])
  const pageCount = Math.max(1, Math.ceil(filteredRows.length / pageSize))
  const currentPage = Math.min(pageIndex, pageCount - 1)
  // Reset pagination when switching run type, scope, players, or completion mode.
  // biome-ignore lint/correctness/useExhaustiveDependencies: these inputs define the viewed collection
  useEffect(() => {
    setPageIndex(0)
  }, [rows, onlyBoth])
  useEffect(() => {
    setPageIndex((index) => Math.min(index, pageCount - 1))
  }, [pageCount])
  const header = (key: SortKey, label: string, playerName?: string) => (
    <Button
      variant="ghost"
      size="sm"
      className="h-8 px-1"
      onClick={() => {
        setSort({ key, desc: sort.key === key ? !sort.desc : key !== "map" })
        setPageIndex(0)
      }}
      aria-label={`${t("compare.sortBy")} ${playerName ? `${playerName} ` : ""}${label}`}
    >
      {label}
      {sort.key === key ? (
        sort.desc ? (
          <ArrowDown className="size-3" />
        ) : (
          <ArrowUp className="size-3" />
        )
      ) : null}
    </Button>
  )
  const delta = (value: number | null | undefined, time: boolean) =>
    value == null ? (
      "—"
    ) : (
      <span
        className={cn(
          "font-mono tabular-nums",
          value < 0
            ? "text-emerald-600 dark:text-emerald-400"
            : value > 0
              ? "text-red-600 dark:text-red-400"
              : "text-muted-foreground",
        )}
      >
        {value < 0 ? "−" : "+"}
        {time
          ? formatRecordTime(Math.abs(value))
          : Math.abs(value).toLocaleString()}
      </span>
    )
  const playerColumns = (
    slot: "player1" | "player2",
    name: string,
  ): ColumnDef<PlayerCompareRunPublic>[] => [
    {
      id: `${slot}.mode`,
      size: 64,
      header: () => header(`${slot}.mode`, t("labels.mode")),
      cell: ({ row }) =>
        row.original[slot] ? <ModeBadge mode={row.original[slot].mode} /> : "—",
    },
    {
      id: `${slot}.teleports`,
      size: 56,
      header: () => header(`${slot}.teleports`, t("labels.tps")),
      cell: ({ row }) =>
        row.original[slot] ? (
          <TeleportsBadge teleports={row.original[slot].teleports} />
        ) : (
          "—"
        ),
    },
    {
      id: `${slot}.time`,
      size: 120,
      header: () => header(`${slot}.time`, name),
      cell: ({ row }) => (
        <span className="font-mono tabular-nums">
          {row.original[slot] ? formatRecordTime(row.original[slot].time) : "—"}
        </span>
      ),
    },
    {
      id: `${slot}.points`,
      size: 80,
      header: () => header(`${slot}.points`, t("labels.points"), name),
      cell: ({ row }) =>
        row.original[slot] ? (
          <PointsBadge points={row.original[slot].points} />
        ) : (
          "—"
        ),
    },
    {
      id: `${slot}.created_on`,
      size: 112,
      header: () =>
        header(`${slot}.created_on`, t("profile.records.date"), name),
      cell: ({ row }) => (
        <FormattedDateTime
          value={row.original[slot]?.created_on}
          display="absolute"
          dateOnly
          fallback="—"
          className="whitespace-nowrap text-xs text-muted-foreground"
        />
      ),
    },
  ]
  const columns: ColumnDef<PlayerCompareRunPublic>[] = [
    {
      id: "map",
      size: 180,
      header: () => header("map", t("labels.map")),
      cell: ({ row }) => (
        <MapDisplay
          mapName={row.original.map_name}
          mapId={row.original.map_id}
        />
      ),
    },
    {
      id: "tier",
      size: 56,
      header: () => header("tier", t("labels.tier")),
      cell: ({ row }) => (
        <TierBadge tier={row.original.map_tier} hideWhenUnknown />
      ),
    },
    ...playerColumns("player1", player1Name),
    {
      id: "time_delta",
      size: 110,
      header: () => header("time_delta", t("compare.timeDelta")),
      cell: ({ row }) => delta(row.original.time_delta, true),
    },
    {
      id: "points_delta",
      size: 110,
      header: () => header("points_delta", t("compare.pointsDelta")),
      cell: ({ row }) => delta(row.original.points_delta, false),
    },
    ...playerColumns("player2", player2Name),
  ]
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          className="w-56"
          aria-label={t("compare.searchMaps")}
          placeholder={t("profile.unfinished.mapSearchPlaceholder")}
          value={filters.map}
          onChange={(event) => update("map", event.target.value)}
        />
        <TierSelector
          value={filters.tier}
          onValueChange={(value) => update("tier", value)}
          showAllLabelInTrigger
          triggerClassName="w-32"
        />
        <ModeSelector
          value={filters.mode}
          onValueChange={(value) => update("mode", value)}
          showAllLabelInTrigger
          triggerClassName="w-32"
        />
        <Select
          value={filters.target}
          onValueChange={(value) => update("target", value)}
        >
          <SelectTrigger
            aria-label={t("compare.filterPlayer")}
            className="w-44"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="either">{t("compare.eitherPlayer")}</SelectItem>
            <SelectItem value="both">{t("compare.bothPlayers")}</SelectItem>
            <SelectItem value="player1">{player1Name}</SelectItem>
            <SelectItem value="player2">{player2Name}</SelectItem>
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          onClick={() => {
            setFilters(EMPTY_FILTERS)
            setPageIndex(0)
          }}
        >
          {t("maps.clearFilters")}
        </Button>
      </div>
      <details className="rounded-xl border p-3">
        <summary className="cursor-pointer text-sm font-medium">
          {t("maps.showFilters")}
        </summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(
            [
              ["minTime", "maxTime", t("compare.timeSeconds")],
              ["minPoints", "maxPoints", t("labels.points")],
              ["minTeleports", "maxTeleports", t("labels.tps")],
            ] as const
          ).map(([min, max, label]) => (
            <div key={min} className="space-y-1">
              <span className="text-xs text-muted-foreground">{label}</span>
              <div className="flex gap-2">
                {([min, max] as const).map((key, index) => (
                  <Input
                    key={key}
                    type="number"
                    min="0"
                    step="any"
                    placeholder={index === 0 ? "Min" : "Max"}
                    aria-label={`${label} ${index === 0 ? "min" : "max"}`}
                    value={filters[key]}
                    onChange={(event) => update(key, event.target.value)}
                  />
                ))}
              </div>
            </div>
          ))}
          <label
            htmlFor="compare-server"
            className="space-y-1 text-xs text-muted-foreground"
          >
            {t("labels.server")}
            <Input
              id="compare-server"
              value={filters.server}
              onChange={(event) => update("server", event.target.value)}
            />
          </label>
          <label
            htmlFor="compare-fromDate"
            className="space-y-1 text-xs text-muted-foreground"
          >
            {t("compare.fromDate")}
            <Input
              type="date"
              id="compare-fromDate"
              value={filters.fromDate}
              onChange={(event) => update("fromDate", event.target.value)}
            />
          </label>
          <label
            htmlFor="compare-toDate"
            className="space-y-1 text-xs text-muted-foreground"
          >
            {t("compare.toDate")}
            <Input
              type="date"
              id="compare-toDate"
              value={filters.toDate}
              onChange={(event) => update("toDate", event.target.value)}
            />
          </label>
        </div>
      </details>
      <div className="overflow-hidden rounded-2xl border bg-card">
        <DataTable
          columns={columns}
          data={filteredRows.slice(
            currentPage * pageSize,
            (currentPage + 1) * pageSize,
          )}
          disablePagination
          showFooter={false}
          emptyText={t("compare.noRuns")}
          tableClassName="[&_th]:px-2 [&_td]:px-2"
          getRowId={(row) => String(row.map_id)}
        />
        <TablePaginationFooter
          totalLabel={t("compare.runs")}
          totalCount={filteredRows.length}
          pageIndex={currentPage}
          pageCount={pageCount}
          pageSize={pageSize}
          onPageIndexChange={setPageIndex}
          onPageSizeChange={(value) => {
            setPageSize(value)
            setPageIndex(0)
          }}
        />
      </div>
    </section>
  )
}
