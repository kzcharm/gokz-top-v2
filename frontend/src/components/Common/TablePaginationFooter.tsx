import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Loader2,
} from "lucide-react"
import { type ReactNode, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { useKeyboardPagination } from "@/components/Common/WASDNavigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { formatNumber } from "@/i18n/locale"

const DEFAULT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const

type TablePaginationFooterProps = {
  totalLabel: ReactNode
  totalCount: number
  pageIndex: number
  pageCount: number
  pageSize: number
  onPageIndexChange: (pageIndex: number) => void
  onPageSizeChange: (pageSize: number) => void
  hasNextPage?: boolean
  hasExactCount?: boolean
  isTotalCountLoading?: boolean
  pageSizeOptions?: readonly number[]
}

export function TablePaginationFooter({
  totalLabel,
  totalCount,
  pageIndex,
  pageCount,
  pageSize,
  onPageIndexChange,
  onPageSizeChange,
  hasNextPage = pageIndex < pageCount - 1,
  hasExactCount = true,
  isTotalCountLoading = false,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
}: TablePaginationFooterProps) {
  const { t } = useTranslation()
  const [pageInputValue, setPageInputValue] = useState(
    `${Math.min(pageIndex + 1, pageCount)}`,
  )
  const keyboardPaginationRef = useKeyboardPagination({
    enabled: pageCount > 1 || hasNextPage,
    canPrevious: pageIndex > 0,
    canNext: hasNextPage || pageIndex < pageCount - 1,
    onPrevious: () => {
      onPageIndexChange(Math.max(0, pageIndex - 1))
    },
    onNext: () => {
      onPageIndexChange(Math.min(pageCount - 1, pageIndex + 1))
    },
  })

  useEffect(() => {
    setPageInputValue(`${Math.min(pageIndex + 1, pageCount)}`)
  }, [pageCount, pageIndex])

  const commitPageInputValue = () => {
    const nextValue = Number(pageInputValue)
    if (!Number.isFinite(nextValue)) {
      setPageInputValue(`${pageIndex + 1}`)
      return
    }

    const nextPage = Math.min(Math.max(Math.trunc(nextValue), 1), pageCount)
    setPageInputValue(`${nextPage}`)
    onPageIndexChange(nextPage - 1)
  }

  return (
    <div className="flex flex-col gap-4 border-t border-border/70 px-6 py-4 text-sm text-muted-foreground sm:px-8 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
        <span>
          {t("pagination.total")}{" "}
          <span className="font-medium text-foreground">
            {formatNumber(totalCount)}
          </span>{" "}
          {totalLabel}
        </span>
        {!hasExactCount || isTotalCountLoading ? (
          <span className="inline-flex items-center gap-1 text-xs">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {t("common.loadingTotal")}
          </span>
        ) : null}
        <div className="flex items-center gap-x-2">
          <span>{t("pagination.rowsPerPage")}</span>
          <Select
            value={`${pageSize}`}
            onValueChange={(value) => {
              onPageSizeChange(Number(value))
            }}
          >
            <SelectTrigger className="h-8 w-[70px]">
              <SelectValue placeholder={pageSize} />
            </SelectTrigger>
            <SelectContent side="top">
              {pageSizeOptions.map((nextPageSize) => (
                <SelectItem key={nextPageSize} value={`${nextPageSize}`}>
                  {nextPageSize}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div
        ref={keyboardPaginationRef}
        className="flex flex-wrap items-center gap-3 lg:justify-end"
      >
        <div className="flex items-center gap-x-1">
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => onPageIndexChange(0)}
            disabled={pageIndex === 0}
          >
            <span className="sr-only">{t("pagination.first")}</span>
            <ChevronsLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => onPageIndexChange(Math.max(0, pageIndex - 1))}
            disabled={pageIndex === 0}
          >
            <span className="sr-only">{t("pagination.previous")}</span>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            max={pageCount}
            value={pageInputValue}
            onChange={(event) => {
              setPageInputValue(event.target.value)
            }}
            onBlur={commitPageInputValue}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault()
                commitPageInputValue()
              }
            }}
            className="h-8 w-14 rounded-md border-border bg-muted px-2 text-center text-sm font-medium text-foreground [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
            aria-label={t("pagination.currentPage", {
              page: pageIndex + 1,
              pageCount,
            })}
          />
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() =>
              onPageIndexChange(Math.min(pageCount - 1, pageIndex + 1))
            }
            disabled={!hasNextPage && pageIndex >= pageCount - 1}
          >
            <span className="sr-only">{t("pagination.next")}</span>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => onPageIndexChange(pageCount - 1)}
            disabled={!hasExactCount || pageIndex >= pageCount - 1}
          >
            <span className="sr-only">{t("pagination.last")}</span>
            <ChevronsRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
