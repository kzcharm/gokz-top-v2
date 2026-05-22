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
  getJumpstatTypeLabel,
  JUMPSTAT_TYPE_OPTIONS,
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { extractErrorMessage } from "@/utils"

const MIN_RATING_OPTIONS = [6, 7, 8, 9, 10] as const

export function JumpstatsLeaderboardTab({ scope }: { scope: AppScope }) {
  const { t } = useTranslation()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
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
    className:
      "cursor-pointer transition-colors hover:bg-muted/30 focus-visible:bg-muted/30 focus-visible:outline-none",
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
      <Tabs
        value={selectedType}
        onValueChange={(value) => {
          setSelectedType(value as JumpstatType)
          setPageIndex(0)
        }}
        className="gap-0"
      >
        <div className="flex flex-wrap items-center gap-3">
          <div className="-mx-2 min-w-0 flex-1 overflow-x-auto px-2 py-1">
            <TabsList
              aria-label={t("leaderboards.jumpstats.jumpType")}
              className="h-auto w-full justify-start gap-2 bg-transparent p-0 text-foreground sm:w-fit"
            >
              {JUMPSTAT_TYPE_OPTIONS.map((option) => (
                <TabsTrigger
                  key={option}
                  value={option}
                  className="h-auto flex-none rounded-full border border-border/60 bg-background/45 px-4 py-2 text-foreground data-[state=active]:bg-background data-[state=active]:shadow-sm dark:data-[state=active]:bg-input/30"
                >
                  {getJumpstatTypeLabel(option, t)}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>

          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Select
              value={String(selectedMinRating)}
              onValueChange={(value) => {
                setSelectedMinRating(Number(value))
                setPageIndex(0)
              }}
            >
              <SelectTrigger
                aria-label={t("leaderboards.jumpstats.minRatingAria")}
                className="h-9 w-[120px] rounded-full border border-[#d9ddea] bg-[#fbfafc] px-4 text-[14px] font-medium text-[#5f677c] shadow-none hover:bg-[#fbfafc] focus-visible:ring-2 focus-visible:ring-[#d9ddea]/70 [&_svg]:text-[#a7adbb]"
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
              variant="ghost"
              className={
                blockEnabled
                  ? "shrink-0 rounded-xl border border-[#7c98d6] bg-[#dbe7ff] text-[#244488] shadow-sm hover:bg-[#cfdfff] hover:text-[#1d3a78]"
                  : "shrink-0 rounded-xl border border-[#c9d7f3] bg-[#eef4ff] text-[#5671aa] hover:bg-[#e3ecff] hover:text-[#3f5d96]"
              }
              onClick={() => {
                setBlockEnabled((current) => !current)
                setPageIndex(0)
              }}
            >
              {t("leaderboards.jumpstats.columns.block")}
            </Button>
          </div>
        </div>
      </Tabs>

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
