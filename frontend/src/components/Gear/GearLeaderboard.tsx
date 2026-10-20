import { useQuery } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  type GearLeaderboardEntry,
  type ProductCategory,
  ProductsService,
} from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"
import { formatNumber } from "@/i18n/locale"
import { CATEGORIES } from "./gear-utils"
import { ProductLink } from "./ProductLink"

export function GearLeaderboard() {
  const { t } = useTranslation()
  const [category, setCategory] = useState<ProductCategory>("mouse")
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "leaderboards.gear.pageSize",
  })
  const result = useQuery({
    queryKey: ["gear-leaderboard", category, pageIndex, pageSize],
    queryFn: () =>
      ProductsService.readGearLeaderboard({
        category,
        skip: pageIndex * pageSize,
        limit: pageSize,
      }),
  })
  const count = result.data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(count / pageSize))
  useEffect(() => {
    if (result.data && pageIndex >= pageCount) setPageIndex(pageCount - 1)
  }, [result.data, pageIndex, pageCount])
  const resize = (size: number) => {
    setPageSize(size)
    setPageIndex(0)
  }
  const columns: ColumnDef<GearLeaderboardEntry>[] = [
    { accessorKey: "rank", header: t("gear.rank") },
    {
      id: "product",
      header: t("gear.product"),
      cell: ({ row }) => <ProductLink product={row.original.product} />,
    },
    {
      accessorKey: "players",
      header: t("gear.players"),
      cell: ({ row }) => formatNumber(row.original.players),
    },
    {
      accessorKey: "share",
      header: t("gear.share"),
      cell: ({ row }) => `${row.original.share.toFixed(1)}%`,
    },
  ]
  return (
    <Card>
      <CardHeader>
        <fieldset
          aria-label={t("gear.category")}
          className="flex flex-wrap gap-2"
        >
          {CATEGORIES.map((value) => (
            <Button
              key={value}
              type="button"
              size="sm"
              variant={category === value ? "default" : "outline"}
              aria-pressed={category === value}
              onClick={() => {
                setCategory(value)
                setPageIndex(0)
              }}
            >
              {t(`gear.categories.${value}`)}
            </Button>
          ))}
        </fieldset>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {result.isError ? (
          <Alert variant="destructive">
            <AlertDescription>
              {t("gear.loadError")}{" "}
              <Button variant="outline" onClick={() => result.refetch()}>
                {t("gear.retry")}
              </Button>
            </AlertDescription>
          </Alert>
        ) : (
          <DataTable
            columns={columns}
            data={result.data?.data ?? []}
            isLoading={result.isPending}
            showFooter={false}
            emptyText={t("gear.noUsage")}
            serverPagination={{
              pageIndex,
              pageSize,
              totalCount: count,
              onPageChange: setPageIndex,
              onPageSizeChange: resize,
            }}
          />
        )}
      </CardContent>
      <TablePaginationFooter
        totalLabel={t("gear.products")}
        totalCount={count}
        pageIndex={pageIndex}
        pageCount={pageCount}
        pageSize={pageSize}
        onPageIndexChange={setPageIndex}
        onPageSizeChange={resize}
      />
    </Card>
  )
}
