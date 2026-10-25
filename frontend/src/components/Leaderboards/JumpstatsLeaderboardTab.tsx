import { useQuery } from "@tanstack/react-query"
import { TriangleAlert } from "lucide-react"
import { type KeyboardEvent, type MouseEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { type JumpstatType, LeaderboardsService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { areRowInteractionsSuppressed } from "@/components/Common/interaction-suppression"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { JumpstatDetailsDialog } from "@/components/Leaderboards/JumpstatDetailsDialog"
import {
  getJumpstatsLeaderboardColumns,
  type JumpstatsLeaderboardTableRow,
} from "@/components/Leaderboards/jumpstats-columns"
import type { AppScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"
import { extractErrorMessage } from "@/utils"
import { JumpstatTypeButtons } from "./JumpstatTypeButtons"

const MIN_RATING_OPTIONS = [6, 7, 8, 9, 10] as const

export function JumpstatsLeaderboardTab({ scope }: { scope: AppScope }) {
  const { t } = useTranslation()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "gokz-page-size-leaderboards-jumpstats",
  })
  const [selectedType, setSelectedType] = useState<JumpstatType>("LJ")
  const [selectedMinRating, setSelectedMinRating] = useState(7)
  const [blockEnabled, setBlockEnabled] = useState(false)
  const [lastKnownTotalCount, setLastKnownTotalCount] = useState(0)
  const [selectedJumpstatId, setSelectedJumpstatId] = useState<string | null>(
    null,
  )

  const sortBy = blockEnabled ? "block" : "distance"
  const leaderboardQuery = useQuery({
    queryKey: [
      "leaderboards",
      "jumpstats",
      scope,
      selectedType,
      selectedMinRating,
      blockEnabled,
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
        minRating: selectedMinRating,
      }),
    staleTime: 30_000,
  })

  const rows: JumpstatsLeaderboardTableRow[] = leaderboardQuery.data?.data ?? []
  const totalCount = leaderboardQuery.data?.count ?? lastKnownTotalCount
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize))
  const hasNextPage = pageIndex + 1 < pageCount
  const columns = getJumpstatsLeaderboardColumns(t, { blockEnabled })

  useEffect(() => {
    if (leaderboardQuery.data === undefined) {
      return
    }
    setLastKnownTotalCount(leaderboardQuery.data.count)
  }, [leaderboardQuery.data])

  useEffect(() => {
    if (leaderboardQuery.data === undefined) {
      return
    }
    if (pageIndex <= pageCount - 1) {
      return
    }
    setPageIndex(pageCount - 1)
  }, [leaderboardQuery.data, pageCount, pageIndex])

  const rowInteractionProps = (row: JumpstatsLeaderboardTableRow) => ({
    className: "cursor-pointer",
    tabIndex: 0,
    onClick: (event: MouseEvent<HTMLTableRowElement>) => {
      if (areRowInteractionsSuppressed()) {
        return
      }
      const target = event.target as HTMLElement
      if (target.closest("a, button, input, select, textarea")) {
        return
      }
      setSelectedJumpstatId(row.id)
    },
    onKeyDown: (event: KeyboardEvent<HTMLTableRowElement>) => {
      if (areRowInteractionsSuppressed()) {
        return
      }
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
      <Card className="gap-0 overflow-hidden rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-6 sm:px-8 sm:pt-8 sm:pb-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <JumpstatTypeButtons
              value={selectedType}
              onValueChange={(value) => {
                setSelectedType(value)
                setPageIndex(0)
              }}
            />

            <div className="flex flex-col gap-3 sm:flex-row lg:flex-wrap lg:items-center lg:justify-end">
              <Select
                value={String(selectedMinRating)}
                onValueChange={(value) => {
                  setSelectedMinRating(Number(value))
                  setPageIndex(0)
                }}
              >
                <SelectTrigger
                  aria-label={t("leaderboards.jumpstats.minRatingAria")}
                  className="data-[size=default]:h-8 w-full sm:w-[132px]"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent align="end">
                  {MIN_RATING_OPTIONS.map((rating) => (
                    <SelectItem key={rating} value={String(rating)}>
                      {t("leaderboards.jumpstats.minRatingValue", {
                        value: rating,
                      })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Button
                type="button"
                size="sm"
                variant={blockEnabled ? "default" : "outline"}
                aria-pressed={blockEnabled}
                onClick={() => {
                  setBlockEnabled((current) => !current)
                  setPageIndex(0)
                }}
              >
                {t("leaderboards.jumpstats.columns.block")}
              </Button>
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

      <Card className="gap-0 overflow-hidden rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
          <DataTable
            columns={columns}
            data={rows}
            isLoading={leaderboardQuery.isLoading}
            emptyText={t("leaderboards.jumpstats.empty")}
            stickyHeader
            stickyHeaderTopClassName="top-0"
            stickyHeaderOffset={64}
            tableClassName="table-fixed border-separate border-spacing-0"
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
