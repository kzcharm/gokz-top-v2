import { useQuery } from "@tanstack/react-query"
import { TriangleAlert } from "lucide-react"
import { type KeyboardEvent, type MouseEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { PlayersService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { JumpstatDetailsDialog } from "@/components/Leaderboards/JumpstatDetailsDialog"
import {
  getJumpstatTypeLabel,
  getProfileJumpstatsColumns,
  JUMPSTAT_TYPE_OPTIONS,
  type ProfileJumpstatsTableRow,
} from "@/components/Leaderboards/jumpstats-columns"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"
import { extractErrorMessage } from "@/utils"

export function ProfileJumpstatsTab({
  identifier,
}: {
  identifier: string | null
}) {
  const { t } = useTranslation()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "gokz-page-size-profile-jumpstats",
  })
  const [selectedType, setSelectedType] =
    useState<(typeof JUMPSTAT_TYPE_OPTIONS)[number]>("LJ")
  const [blockEnabled, setBlockEnabled] = useState(false)
  const [lastKnownTotalCount, setLastKnownTotalCount] = useState(0)
  const [selectedJumpstatId, setSelectedJumpstatId] = useState<string | null>(
    null,
  )

  const sortBy = blockEnabled ? "block" : "distance"
  const jumpstatsQuery = useQuery({
    queryKey: [
      "profile-jumpstats",
      identifier,
      selectedType,
      blockEnabled,
      pageIndex,
      pageSize,
      sortBy,
    ],
    queryFn: () =>
      PlayersService.readPlayerJumpstats({
        identifier: identifier ?? "",
        type: selectedType,
        offset: pageIndex * pageSize,
        limit: pageSize,
        sortBy,
        sortOrder: "desc",
      }),
    enabled: identifier !== null,
    retry: false,
    staleTime: 30_000,
  })

  const rows: ProfileJumpstatsTableRow[] = jumpstatsQuery.data?.data ?? []
  const totalCount = jumpstatsQuery.data?.count ?? lastKnownTotalCount
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize))
  const hasNextPage = pageIndex + 1 < pageCount
  const columns = getProfileJumpstatsColumns(t, { blockEnabled })

  useEffect(() => {
    if (identifier === null) {
      return
    }
    setPageIndex(0)
    setLastKnownTotalCount(0)
    setSelectedJumpstatId(null)
  }, [identifier])

  useEffect(() => {
    if (jumpstatsQuery.data === undefined) {
      return
    }
    setLastKnownTotalCount(jumpstatsQuery.data.count)
  }, [jumpstatsQuery.data])

  useEffect(() => {
    if (jumpstatsQuery.data === undefined) {
      return
    }
    if (pageIndex <= pageCount - 1) {
      return
    }
    setPageIndex(pageCount - 1)
  }, [jumpstatsQuery.data, pageCount, pageIndex])

  const rowInteractionProps = (row: ProfileJumpstatsTableRow) => ({
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

  if (identifier === null) {
    return null
  }

  return (
    <div className="space-y-6">
      <Tabs
        value={selectedType}
        onValueChange={(value) => {
          setSelectedType(value as (typeof JUMPSTAT_TYPE_OPTIONS)[number])
          setPageIndex(0)
        }}
        className="gap-0"
      >
        <div className="flex items-center gap-3">
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

          <Button
            type="button"
            variant="ghost"
            className={
              blockEnabled
                ? "ml-auto shrink-0 rounded-xl border border-[#7c98d6] bg-[#dbe7ff] text-[#244488] shadow-sm hover:bg-[#cfdfff] hover:text-[#1d3a78]"
                : "ml-auto shrink-0 rounded-xl border border-[#c9d7f3] bg-[#eef4ff] text-[#5671aa] hover:bg-[#e3ecff] hover:text-[#3f5d96]"
            }
            onClick={() => {
              setBlockEnabled((current) => !current)
              setPageIndex(0)
            }}
          >
            {t("leaderboards.jumpstats.columns.block")}
          </Button>
        </div>
      </Tabs>

      {jumpstatsQuery.isError ? (
        <Alert variant="destructive">
          <TriangleAlert className="h-4 w-4" />
          <AlertTitle>{t("profile.jumpstats.loadFailedTitle")}</AlertTitle>
          <AlertDescription>
            {extractErrorMessage(jumpstatsQuery.error) ||
              t("profile.jumpstats.loadFailedBody")}
          </AlertDescription>
        </Alert>
      ) : null}

      <Card className="gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
          <DataTable
            columns={columns}
            data={rows}
            isLoading={jumpstatsQuery.isLoading}
            emptyText={t("profile.jumpstats.empty")}
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
          />
          <TablePaginationFooter
            totalLabel={t("profile.tabs.jumpstats")}
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
