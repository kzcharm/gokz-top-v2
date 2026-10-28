import type { ColumnDef } from "@tanstack/react-table"
import { ArrowDown, ArrowUp } from "lucide-react"
import { type ReactNode, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import type { PlayerCompareRunPublic, RecordPublic } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapDisplay } from "@/components/Common/MapDisplay"
import {
  ModeSelector,
  type ModeSelectorValue,
} from "@/components/Common/ModeSelector"
import {
  PlayerDisplay,
  type PlayerDisplayPlayer,
} from "@/components/Common/PlayerDisplay"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import {
  TierSelector,
  type TierSelectorValue,
} from "@/components/Common/TierSelector"
import { ModeBadge } from "@/components/Records/ModeBadge"
import { PointsBadge } from "@/components/Records/PointsBadge"
import { TeleportsBadge } from "@/components/Records/TeleportsBadge"
import { formatRecordTime } from "@/components/Records/utils"
import { formatWrGap, getWrGap } from "@/components/Records/wr-gap"
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
import { COMPARE_PLAYER_COLORS } from "./compare-player"

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
  headerControls,
  player1,
  player2,
}: {
  rows: PlayerCompareRunPublic[]
  player1Name: string
  player2Name: string
  onlyBoth: boolean
  headerControls?: ReactNode
  player1: PlayerDisplayPlayer
  player2: PlayerDisplayPlayer
}) {
  const { t } = useTranslation()
  const [gapMode, setGapMode] = useState<"difference" | "ratio">(() => {
    try {
      return localStorage.getItem("compare-time-gap-mode") === "difference"
        ? "difference"
        : "ratio"
    } catch {
      return "ratio"
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem("compare-time-gap-mode", gapMode)
    } catch {
      // Keep the control usable when browser storage is unavailable.
    }
  }, [gapMode])
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
  const wins = useMemo(() => {
    const counts = { player1: 0, player2: 0 }
    for (const row of filteredRows) {
      if (!row.player1 || !row.player2) continue
      if (row.player1.time < row.player2.time) counts.player1++
      else if (row.player2.time < row.player1.time) counts.player2++
    }
    return counts
  }, [filteredRows])
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
  const delta = (
    row: PlayerCompareRunPublic,
    slot: "player1" | "player2",
    field: "time" | "points",
  ) => {
    const record = row[slot]
    const other = row[slot === "player1" ? "player2" : "player1"]
    if (!record || !other || record[field] <= other[field]) return null
    const difference = record[field] - other[field]
    return (
      <span
        data-testid={`compare-${field}-delta`}
        className={cn(
          "text-xs font-mono tabular-nums",
          field === "time"
            ? "text-red-600 dark:text-red-400"
            : "text-emerald-600 dark:text-emerald-400",
        )}
      >
        (
        {gapMode === "ratio" && field === "time"
          ? formatWrGap(getWrGap(record[field], other[field]))
          : `+${field === "time" ? formatRecordTime(difference) : difference.toLocaleString()}`}
        )
      </span>
    )
  }
  const slots = ["player1", "player2"] as const
  const stacked = (render: (slot: "player1" | "player2") => ReactNode) => (
    <div className="-mx-3 grid grid-rows-2 divide-y divide-border/20">
      {slots.map((slot) => (
        <div
          key={slot}
          data-player={slot}
          className="flex h-11 items-center gap-2 whitespace-nowrap px-3"
          style={{
            backgroundColor: `color-mix(in srgb, ${COMPARE_PLAYER_COLORS[slot]} 7%, transparent)`,
          }}
        >
          {render(slot)}
        </div>
      ))}
    </div>
  )
  const recordHeader = (
    field: "mode" | "teleports" | "time" | "points" | "created_on",
    label: string,
  ) => {
    const active =
      sort.key === `player1.${field}` || sort.key === `player2.${field}`
    const slot = sort.key.startsWith("player2.") ? "player2" : "player1"
    return (
      <Button
        variant="ghost"
        size="sm"
        className="h-8 px-1"
        aria-label={`${t("compare.sortBy")} ${label}`}
        onClick={() => {
          if (!active) setSort({ key: `player1.${field}`, desc: false })
          else if (!sort.desc) setSort({ key: `${slot}.${field}`, desc: true })
          else
            setSort({
              key: `${slot === "player1" ? "player2" : "player1"}.${field}`,
              desc: false,
            })
          setPageIndex(0)
        }}
      >
        {label}
        {active && (
          <span
            className="inline-flex items-center gap-1 text-xs text-primary"
            title={slot === "player1" ? player1Name : player2Name}
          >
            {slot === "player1" ? "P1" : "P2"}
            {sort.desc ? (
              <ArrowDown className="size-3" />
            ) : (
              <ArrowUp className="size-3" />
            )}
          </span>
        )}
      </Button>
    )
  }
  const recordColumns: ColumnDef<PlayerCompareRunPublic>[] = [
    {
      id: "player",
      size: 150,
      header: () => t("labels.player"),
      cell: () =>
        stacked((slot) => (
          <>
            <span
              aria-hidden="true"
              className="size-2 shrink-0 rounded-full"
              style={{ backgroundColor: COMPARE_PLAYER_COLORS[slot] }}
            />
            <PlayerDisplay
              player={slot === "player1" ? player1 : player2}
              compact
              showRatingIcon={false}
              showAvatar={false}
              showCountryFlag={false}
            />
          </>
        )),
    },
    ...(["time", "points", "mode", "teleports", "created_on"] as const).map(
      (field): ColumnDef<PlayerCompareRunPublic> => ({
        id: field,
        size:
          field === "created_on"
            ? 120
            : field === "time"
              ? 180
              : field === "points"
                ? 150
                : 80,
        header: () =>
          recordHeader(
            field,
            field === "created_on"
              ? t("profile.records.date")
              : field === "teleports"
                ? t("labels.tps")
                : t(`labels.${field}`),
          ),
        cell: ({ row }) =>
          stacked((slot) => {
            const record = row.original[slot]
            if (!record) return <span className="text-muted-foreground">—</span>
            if (field === "mode") return <ModeBadge mode={record.mode} />
            if (field === "teleports")
              return <TeleportsBadge teleports={record.teleports} />
            if (field === "points")
              return (
                <>
                  <PointsBadge points={record.points} />
                  {delta(row.original, slot, "points")}
                </>
              )
            if (field === "created_on")
              return (
                <FormattedDateTime
                  value={record.created_on}
                  display="absolute"
                  dateOnly
                  className="text-xs text-muted-foreground"
                />
              )
            return (
              <>
                <span className="font-mono tabular-nums">
                  {formatRecordTime(record.time)}
                </span>
                {delta(row.original, slot, "time")}
              </>
            )
          }),
      }),
    ),
  ]
  const columns: ColumnDef<PlayerCompareRunPublic>[] = [
    {
      id: "map",
      size: 180,
      header: () => header("map", t("labels.map")),
      cell: ({ row }) => (
        <MapDisplay
          className="bg-muted dark:bg-muted"
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
    ...recordColumns,
  ]
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <h2 className="text-lg font-semibold">{t("compare.runs")}</h2>
          <div
            className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm"
            aria-live="polite"
          >
            <span
              className="text-muted-foreground"
              title={t("compare.winningMapsHint")}
            >
              {t("compare.winningMaps")}
            </span>
            {slots.map((slot) => (
              <div
                key={slot}
                className="flex items-center gap-2"
                data-testid={`compare-wins-${slot}`}
              >
                <span
                  aria-hidden="true"
                  className="size-2 rounded-full"
                  style={{ backgroundColor: COMPARE_PLAYER_COLORS[slot] }}
                />
                <PlayerDisplay
                  player={slot === "player1" ? player1 : player2}
                  compact
                  showAvatar={false}
                  showCountryFlag={false}
                  showRatingIcon={false}
                />
                <strong
                  className="font-mono tabular-nums"
                  data-testid={`compare-win-count-${slot}`}
                >
                  {wins[slot].toLocaleString()}
                </strong>
              </div>
            ))}
          </div>
        </div>
        {headerControls}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <fieldset
          className="inline-flex items-center rounded-lg border p-1"
          aria-label={t("compare.gapDisplay")}
        >
          {(["difference", "ratio"] as const).map((mode) => (
            <Button
              key={mode}
              size="sm"
              variant={gapMode === mode ? "secondary" : "ghost"}
              aria-pressed={gapMode === mode}
              onClick={() => setGapMode(mode)}
            >
              {t(`compare.${mode}`)}
            </Button>
          ))}
        </fieldset>
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
          tableClassName="[&_th]:px-3 [&_td]:px-3 [&_td]:py-0 [&_td]:bg-card [&_tbody>tr:not(:last-child)]:border-b-2 [&_tbody>tr:not(:last-child)]:border-foreground/25"
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
