import { useQuery } from "@tanstack/react-query"
import {
  functionalUpdate,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table"
import { Filter, TriangleAlert } from "lucide-react"
import {
  type KeyboardEvent,
  type MouseEvent,
  useEffect,
  useMemo,
  useState,
} from "react"
import { useTranslation } from "react-i18next"

import { type JumpstatType, LeaderboardsService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { JumpstatDetailsDialog } from "@/components/Leaderboards/JumpstatDetailsDialog"
import {
  getJumpstatsLeaderboardColumns,
  type JumpstatsLeaderboardTableRow,
} from "@/components/Leaderboards/jumpstats-columns"
import type { AppScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { extractErrorMessage } from "@/utils"

const JUMPSTAT_TYPE_OPTIONS: JumpstatType[] = [
  "LJ",
  "BH",
  "MBH",
  "WJ",
  "LAJ",
  "LAH",
  "JB",
  "LBH",
  "LWJ",
  "FL",
  "UNK",
  "INV",
]

function getJumpstatTypeLabel(
  value: JumpstatType,
  t: ReturnType<typeof useTranslation>["t"],
) {
  return t(`leaderboards.jumpstats.types.${value}`)
}

export function JumpstatsLeaderboardTab({ scope }: { scope: AppScope }) {
  const { t } = useTranslation()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [selectedType, setSelectedType] = useState<JumpstatType>("LJ")
  const [selectedJumpstatId, setSelectedJumpstatId] = useState<string | null>(
    null,
  )
  const [sorting, setSorting] = useState<SortingState>([
    { id: "distance", desc: true },
  ])

  const sortBy = sorting[0]?.id === "block" ? "block" : "distance"
  const leaderboardQuery = useQuery({
    queryKey: [
      "leaderboards",
      "jumpstats",
      scope,
      selectedType,
      pageIndex,
      pageSize,
      sortBy,
    ],
    queryFn: () =>
      LeaderboardsService.readJumpstatLeaderboard({
        scope,
        type: selectedType,
        offset: pageIndex * pageSize,
        limit: pageSize,
        sortBy,
      }),
    staleTime: 30_000,
  })

  const rows = useMemo<JumpstatsLeaderboardTableRow[]>(
    () => leaderboardQuery.data?.data ?? [],
    [leaderboardQuery.data],
  )
  const totalCount = leaderboardQuery.data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize))
  const hasNextPage = pageIndex + 1 < pageCount
  const columns = useMemo(() => getJumpstatsLeaderboardColumns(t), [t])

  const onSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = functionalUpdate(updater, sorting)
    const nextSort =
      next[0]?.id === "block"
        ? [{ id: "block", desc: true }]
        : [{ id: "distance", desc: true }]
    setSorting(nextSort)
    setPageIndex(0)
  }

  useEffect(() => {
    if (pageIndex <= pageCount - 1) {
      return
    }
    setPageIndex(pageCount - 1)
  }, [pageCount, pageIndex])

  const rowInteractionProps = (row: JumpstatsLeaderboardTableRow) => ({
    className:
      "cursor-pointer transition-colors hover:bg-muted/30 focus-visible:bg-muted/30 focus-visible:outline-none",
    tabIndex: 0,
    onClick: (event: MouseEvent<HTMLTableRowElement>) => {
      const target = event.target as HTMLElement
      if (target.closest("a, button, input, select, textarea")) {
        return
      }
      setSelectedJumpstatId(row.id)
    },
    onKeyDown: (event: KeyboardEvent<HTMLTableRowElement>) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return
      }
      const target = event.target as HTMLElement
      if (target.closest("a, button, input, select, textarea")) {
        return
      }
      event.preventDefault()
      setSelectedJumpstatId(row.id)
    },
  })

  return (
    <div className="space-y-6">
      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 sm:px-8 sm:pt-8 sm:pb-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-2 rounded-full border border-border/70 bg-background/70 px-3 py-2 text-sm text-muted-foreground">
              <Filter className="size-4" />
              <span>{t("leaderboards.jumpstats.filters")}</span>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <span className="text-sm font-medium text-foreground">
                {t("leaderboards.jumpstats.jumpType")}
              </span>
              <Select
                value={selectedType}
                onValueChange={(value) => {
                  setSelectedType(value as JumpstatType)
                  setPageIndex(0)
                }}
              >
                <SelectTrigger
                  className="w-full min-w-[220px] sm:w-[220px]"
                  aria-label={t("leaderboards.jumpstats.jumpType")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {JUMPSTAT_TYPE_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {getJumpstatTypeLabel(option, t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {leaderboardQuery.isError ? (
        <Alert variant="destructive">
          <TriangleAlert className="h-4 w-4" />
          <AlertTitle>{t("leaderboards.jumpstats.loadFailedTitle")}</AlertTitle>
          <AlertDescription>
            {extractErrorMessage(leaderboardQuery.error) ||
              t("leaderboards.jumpstats.loadFailedDescription")}
          </AlertDescription>
        </Alert>
      ) : null}

      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
          <DataTable
            columns={columns}
            data={rows}
            isLoading={leaderboardQuery.isLoading}
            emptyText={t("leaderboards.jumpstats.empty")}
            stickyHeader
            stickyHeaderTopClassName="top-16"
            tableContainerClassName="md:overflow-visible"
            tableClassName="border-separate border-spacing-0"
            showFooter={false}
            getRowId={(row) => row.id}
            getRowProps={rowInteractionProps}
            serverPagination={{
              pageIndex,
              pageSize,
              totalCount,
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
            totalLabel={t("nav.players")}
            totalCount={totalCount}
            pageIndex={pageIndex}
            pageCount={pageCount}
            pageSize={pageSize}
            onPageIndexChange={setPageIndex}
            onPageSizeChange={(size) => {
              setPageSize(size)
              setPageIndex(0)
            }}
            hasNextPage={hasNextPage}
          />
        </CardContent>
      </Card>

      <JumpstatDetailsDialog
        jumpstatId={selectedJumpstatId}
        open={selectedJumpstatId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedJumpstatId(null)
          }
        }}
      />
    </div>
  )
}
