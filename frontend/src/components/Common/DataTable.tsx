import {
  type ColumnDef,
  flexRender,
  functionalUpdate,
  getCoreRowModel,
  getPaginationRowModel,
  type OnChangeFn,
  type PaginationState,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table"
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Loader2,
} from "lucide-react"
import {
  type ComponentProps,
  Fragment,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from "react"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { RowContextMenu } from "./RowContextMenu"

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  isLoading?: boolean
  emptyText?: string
  stickyHeader?: boolean
  stickyHeaderTopClassName?: string
  stickyHeaderPinnedClassName?: string
  stickyHeaderOffset?: number
  tableContainerClassName?: string
  tableClassName?: string
  showFooter?: boolean
  footerSummary?: ReactNode
  pageInputEnabled?: boolean
  getRowClassName?: (row: TData) => string | undefined
  getRowProps?: (row: TData) => ComponentProps<typeof TableRow> | undefined
  getRowContextMenu?: (row: TData) => ReactNode
  getRowId?: (row: TData) => string
  expandedRowId?: string | null
  renderExpandedContent?: (row: TData) => ReactNode
  serverPagination?: {
    pageIndex: number
    pageSize: number
    totalCount: number
    onPageChange: (pageIndex: number) => void
    onPageSizeChange: (pageSize: number) => void
  }
  sorting?: {
    state: SortingState
    onSortingChange: OnChangeFn<SortingState>
    manualSorting?: boolean
  }
}

function DataTableBodyRow<TData, TValue>({
  columns,
  getColumnMeta,
  getColumnSizeStyle,
  getRowClassName,
  renderExpandedContent,
  row,
  rowContextMenu,
  rowProps,
  expandedRowId,
  getRowId,
}: {
  columns: ColumnDef<TData, TValue>[]
  getColumnMeta: (columnDef: ColumnDef<TData, TValue>) =>
    | {
        headerClassName?: string
        cellClassName?: string
      }
    | undefined
  getColumnSizeStyle: (
    columnDef: ColumnDef<TData, TValue>,
  ) => { width: string; minWidth: string } | undefined
  getRowClassName?: (row: TData) => string | undefined
  renderExpandedContent?: (row: TData) => ReactNode
  row: ReturnType<
    ReturnType<typeof useReactTable<TData>>["getRowModel"]
  >["rows"][number]
  rowContextMenu: ReactNode
  rowProps?: ComponentProps<typeof TableRow>
  expandedRowId?: string | null
  getRowId?: (row: TData) => string
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuPosition, setMenuPosition] = useState<{
    x: number
    y: number
  } | null>(null)
  const resolvedRowId = getRowId?.(row.original) ?? row.id
  const isExpanded =
    renderExpandedContent !== undefined && expandedRowId === resolvedRowId
  const rowClassName = rowProps?.className ?? getRowClassName?.(row.original)

  const rowElement = (
    <TableRow
      {...rowProps}
      className={rowClassName}
      onContextMenu={
        rowContextMenu
          ? (event: MouseEvent<HTMLTableRowElement>) => {
              rowProps?.onContextMenu?.(event)
              if (event.defaultPrevented) {
                return
              }
              event.preventDefault()
              setMenuPosition({ x: event.clientX, y: event.clientY })
              setMenuOpen(true)
            }
          : rowProps?.onContextMenu
      }
      onKeyDown={
        rowContextMenu
          ? (event: KeyboardEvent<HTMLTableRowElement>) => {
              rowProps?.onKeyDown?.(event)
              if (event.defaultPrevented) {
                return
              }
              if (
                event.key === "ContextMenu" ||
                (event.shiftKey && event.key === "F10")
              ) {
                event.preventDefault()
                const rect = event.currentTarget.getBoundingClientRect()
                setMenuPosition({ x: rect.left, y: rect.bottom })
                setMenuOpen(true)
              }
            }
          : rowProps?.onKeyDown
      }
      tabIndex={rowContextMenu ? 0 : rowProps?.tabIndex}
    >
      {row.getVisibleCells().map((cell) => {
        const columnMeta = getColumnMeta(cell.column.columnDef)
        return (
          <TableCell
            key={cell.id}
            className={columnMeta?.cellClassName}
            style={getColumnSizeStyle(cell.column.columnDef)}
          >
            {flexRender(cell.column.columnDef.cell, cell.getContext())}
          </TableCell>
        )
      })}
    </TableRow>
  )

  const rowFragment = (
    <Fragment key={row.id}>
      {rowElement}
      {isExpanded ? (
        <TableRow className="bg-muted/15 hover:bg-muted/15">
          <TableCell colSpan={columns.length} className="px-4 py-4">
            {renderExpandedContent(row.original)}
          </TableCell>
        </TableRow>
      ) : null}
    </Fragment>
  )

  if (rowContextMenu === null) {
    return rowFragment
  }

  return (
    <Fragment key={row.id}>
      {rowFragment}
      <RowContextMenu
        open={menuOpen}
        onOpenChange={(open) => {
          setMenuOpen(open)
          if (!open) {
            setMenuPosition(null)
          }
        }}
        position={menuPosition}
      >
        {rowContextMenu}
      </RowContextMenu>
    </Fragment>
  )
}

export function DataTable<TData, TValue>({
  columns,
  data,
  isLoading = false,
  emptyText = "No results found.",
  stickyHeader = false,
  stickyHeaderTopClassName = "top-0",
  stickyHeaderPinnedClassName,
  stickyHeaderOffset = 0,
  tableContainerClassName,
  tableClassName,
  showFooter = true,
  footerSummary,
  pageInputEnabled = false,
  getRowClassName,
  getRowProps,
  getRowContextMenu,
  getRowId,
  expandedRowId,
  renderExpandedContent,
  serverPagination,
  sorting,
}: DataTableProps<TData, TValue>) {
  const getColumnSizeStyle = (columnDef: ColumnDef<TData, TValue>) => {
    if (typeof columnDef.size !== "number") {
      return undefined
    }

    return {
      width: `${columnDef.size}px`,
      minWidth: `${columnDef.size}px`,
    }
  }

  const getColumnMeta = (columnDef: ColumnDef<TData, TValue>) =>
    (columnDef.meta as
      | {
          headerClassName?: string
          cellClassName?: string
        }
      | undefined) ?? undefined

  const { t } = useTranslation()
  const tableContainerRef = useRef<HTMLDivElement | null>(null)
  const stickyHeaderCellRef = useRef<HTMLTableCellElement | null>(null)
  const isStickyHeaderPinnedRef = useRef(false)
  const [isStickyHeaderPinned, setIsStickyHeaderPinned] = useState(false)
  const paginationState = serverPagination
    ? {
        pageIndex: serverPagination.pageIndex,
        pageSize: serverPagination.pageSize,
      }
    : undefined

  const handlePaginationChange: OnChangeFn<PaginationState> | undefined =
    serverPagination
      ? (updater) => {
          const current: PaginationState = {
            pageIndex: serverPagination.pageIndex,
            pageSize: serverPagination.pageSize,
          }
          const next = functionalUpdate(updater, current)

          if (next.pageSize !== current.pageSize) {
            serverPagination.onPageSizeChange(next.pageSize)
          }

          if (next.pageIndex !== current.pageIndex) {
            serverPagination.onPageChange(next.pageIndex)
          }
        }
      : undefined

  const table = useReactTable({
    data,
    columns,
    state: {
      ...(paginationState ? { pagination: paginationState } : {}),
      ...(sorting ? { sorting: sorting.state } : {}),
    },
    onPaginationChange: handlePaginationChange,
    onSortingChange: sorting?.onSortingChange,
    manualPagination: Boolean(serverPagination),
    manualSorting: sorting?.manualSorting ?? false,
    pageCount: serverPagination
      ? Math.max(
          1,
          Math.ceil(serverPagination.totalCount / serverPagination.pageSize),
        )
      : undefined,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  })

  const totalCount = serverPagination
    ? serverPagination.totalCount
    : data.length
  const pageIndex = table.getState().pagination.pageIndex
  const pageCount = table.getPageCount()
  const [pageInputValue, setPageInputValue] = useState(`${pageIndex + 1}`)
  const hasPaginationFooter = Boolean(
    showFooter && (serverPagination || pageCount > 1),
  )
  const keyboardPaginationRef = useKeyboardPagination({
    enabled: hasPaginationFooter,
    canPrevious: table.getCanPreviousPage(),
    canNext: table.getCanNextPage(),
    onPrevious: () => table.previousPage(),
    onNext: () => table.nextPage(),
  })

  useEffect(() => {
    setPageInputValue(`${pageIndex + 1}`)
  }, [pageIndex])

  useEffect(() => {
    if (!stickyHeader) {
      isStickyHeaderPinnedRef.current = false
      setIsStickyHeaderPinned(false)
      return
    }

    let animationFrame: number | null = null

    const setPinnedState = (isPinned: boolean) => {
      if (isStickyHeaderPinnedRef.current === isPinned) {
        return
      }
      isStickyHeaderPinnedRef.current = isPinned
      setIsStickyHeaderPinned(isPinned)
    }

    const updateStickyHeaderPinnedState = () => {
      const container = tableContainerRef.current
      const stickyHeaderCell = stickyHeaderCellRef.current

      if (!container || !stickyHeaderCell) {
        setPinnedState(false)
        return
      }

      const stickyTop = Number.parseFloat(
        window.getComputedStyle(stickyHeaderCell).top,
      )
      const containerRect = container.getBoundingClientRect()
      const stickyHeaderHeight = stickyHeaderCell.getBoundingClientRect().height
      const stickyOffset = Math.max(0, stickyHeaderOffset)
      const translateY =
        stickyOffset > 0
          ? Math.max(0, stickyOffset - Math.max(containerRect.top, 0))
          : 0
      const isWithinStickyRange =
        containerRect.bottom > stickyOffset + stickyHeaderHeight

      container.style.setProperty(
        "--sticky-header-translate-y",
        isWithinStickyRange ? `${translateY}px` : "0px",
      )
      setPinnedState(
        Number.isFinite(stickyTop) &&
          isWithinStickyRange &&
          (containerRect.top <= stickyTop || translateY > 0),
      )
    }

    const scheduleStickyHeaderUpdate = () => {
      if (animationFrame !== null) {
        return
      }
      animationFrame = window.requestAnimationFrame(() => {
        animationFrame = null
        updateStickyHeaderPinnedState()
      })
    }

    updateStickyHeaderPinnedState()
    window.addEventListener("scroll", scheduleStickyHeaderUpdate, {
      passive: true,
    })
    window.addEventListener("resize", scheduleStickyHeaderUpdate)

    return () => {
      if (animationFrame !== null) {
        window.cancelAnimationFrame(animationFrame)
      }
      tableContainerRef.current?.style.removeProperty(
        "--sticky-header-translate-y",
      )
      window.removeEventListener("scroll", scheduleStickyHeaderUpdate)
      window.removeEventListener("resize", scheduleStickyHeaderUpdate)
    }
  }, [stickyHeader, stickyHeaderOffset])

  const commitPageInputValue = () => {
    if (!pageInputEnabled) {
      return
    }

    const parsedPage = Number(pageInputValue)
    if (!Number.isFinite(parsedPage)) {
      setPageInputValue(`${pageIndex + 1}`)
      return
    }

    const nextPage = Math.min(Math.max(Math.trunc(parsedPage), 1), pageCount)
    table.setPageIndex(nextPage - 1)
    setPageInputValue(`${nextPage}`)
  }

  return (
    <div ref={keyboardPaginationRef} className="flex flex-col gap-4">
      <Table
        ref={tableContainerRef}
        containerClassName={tableContainerClassName}
        className={tableClassName}
      >
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id} className="hover:bg-transparent">
              {headerGroup.headers.map((header) => {
                const columnMeta = getColumnMeta(header.column.columnDef)
                return (
                  <TableHead
                    key={header.id}
                    ref={
                      header.id === headerGroup.headers[0]?.id
                        ? stickyHeaderCellRef
                        : undefined
                    }
                    className={[
                      stickyHeader
                        ? `sticky ${stickyHeaderTopClassName} z-20 bg-muted ${
                            isStickyHeaderPinned
                              ? [
                                  "first:rounded-tl-none last:rounded-tr-none",
                                  stickyHeaderPinnedClassName,
                                ]
                                  .filter(Boolean)
                                  .join(" ")
                              : "first:rounded-tl-[27px] last:rounded-tr-[27px]"
                          }`
                        : undefined,
                      columnMeta?.headerClassName,
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    style={{
                      ...getColumnSizeStyle(header.column.columnDef),
                      ...(stickyHeaderOffset > 0
                        ? {
                            transform:
                              "translateY(var(--sticky-header-translate-y, 0px))",
                          }
                        : {}),
                    }}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                )
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.length ? (
            table.getRowModel().rows.map((row) => {
              const rowProps = getRowProps?.(row.original)
              const rowContextMenu = getRowContextMenu?.(row.original) ?? null
              return (
                <DataTableBodyRow
                  key={row.id}
                  columns={columns}
                  expandedRowId={expandedRowId}
                  getColumnMeta={getColumnMeta}
                  getColumnSizeStyle={getColumnSizeStyle}
                  getRowClassName={getRowClassName}
                  getRowId={getRowId}
                  renderExpandedContent={renderExpandedContent}
                  row={row}
                  rowContextMenu={rowContextMenu}
                  rowProps={rowProps}
                />
              )
            })
          ) : (
            <TableRow className="hover:bg-transparent">
              <TableCell
                colSpan={columns.length}
                className="h-32 text-center text-muted-foreground"
              >
                {isLoading ? (
                  <div className="flex items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  emptyText
                )}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      {hasPaginationFooter && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 border-t bg-muted/20">
          <div className="flex flex-col sm:flex-row sm:items-center gap-4">
            <div className="text-sm text-muted-foreground">
              {footerSummary ?? (
                <>
                  {t("pagination.total")}{" "}
                  <span className="font-medium text-foreground">
                    {totalCount}
                  </span>{" "}
                  {t("pagination.entries")}
                </>
              )}
            </div>
            <div className="flex items-center gap-x-2">
              <p className="text-sm text-muted-foreground">
                {t("pagination.rowsPerPage")}
              </p>
              <Select
                value={`${table.getState().pagination.pageSize}`}
                onValueChange={(value) => {
                  table.setPageSize(Number(value))
                  table.setPageIndex(0)
                }}
              >
                <SelectTrigger className="h-8 w-[70px]">
                  <SelectValue
                    placeholder={table.getState().pagination.pageSize}
                  />
                </SelectTrigger>
                <SelectContent side="top">
                  {[10, 20, 50, 100].map((pageSize) => (
                    <SelectItem key={pageSize} value={`${pageSize}`}>
                      {pageSize}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center gap-x-6">
            <div className="flex items-center gap-x-1 text-sm text-muted-foreground">
              <span>{t("pagination.page")}</span>
              {pageInputEnabled ? (
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
                  className="h-8 w-20 text-center [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                  aria-label={t("pagination.currentPageShort")}
                />
              ) : (
                <span className="font-medium text-foreground">
                  {pageIndex + 1}
                </span>
              )}
              <span>{t("pagination.of")}</span>
              <span className="font-medium text-foreground">{pageCount}</span>
            </div>

            <div className="flex items-center gap-x-1">
              <Button
                variant="outline"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => table.setPageIndex(0)}
                disabled={!table.getCanPreviousPage()}
              >
                <span className="sr-only">{t("pagination.first")}</span>
                <ChevronsLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 w-12 p-0"
                onClick={() => table.previousPage()}
                disabled={!table.getCanPreviousPage()}
              >
                <span className="sr-only">{t("pagination.previous")}</span>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 w-12 p-0"
                onClick={() => table.nextPage()}
                disabled={!table.getCanNextPage()}
              >
                <span className="sr-only">{t("pagination.next")}</span>
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => table.setPageIndex(table.getPageCount() - 1)}
                disabled={!table.getCanNextPage()}
              >
                <span className="sr-only">{t("pagination.last")}</span>
                <ChevronsRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
