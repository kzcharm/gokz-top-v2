import { useQuery } from "@tanstack/react-query"
import { startTransition, useMemo, useState } from "react"

import { type MapReviewPublic, MapsService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { extractErrorMessage } from "@/utils"

import { getReviewColumns, type ReviewTableRow } from "./columns"

const DEFAULT_PAGE_SIZE = 20
const COMMENT_EXPAND_THRESHOLD = 180

type LanguagePreset = "all" | "en" | "zh" | "ru"

function mapReviewRow(review: MapReviewPublic): ReviewTableRow {
  return {
    id: `${review.steamid64}-${review.map_id}`,
    steamid64: review.steamid64,
    map_id: review.map_id,
    updated_at: review.updated_at,
    player: review.player,
    map: review.map,
    overall: review.content.overall,
    gameplay: review.content.gameplay ?? null,
    visuals: review.content.visuals ?? null,
    comment: review.content.comment?.text ?? null,
    hasLongComment:
      (review.content.comment?.text?.trim().length ?? 0) >
      COMMENT_EXPAND_THRESHOLD,
  }
}

export function ReviewsDashboardPanel() {
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [expandedReviewId, setExpandedReviewId] = useState<string | null>(null)
  const [withCommentsOnly, setWithCommentsOnly] = useState(true)
  const [languagePreset, setLanguagePreset] = useState<LanguagePreset>("all")

  const reviewsQuery = useQuery({
    queryKey: [
      "dashboard",
      "reviews",
      pageIndex,
      pageSize,
      withCommentsOnly,
      languagePreset,
    ],
    queryFn: () =>
      MapsService.readMapReviews({
        offset: pageIndex * pageSize,
        limit: pageSize,
        withCommentsOnly,
        language: languagePreset === "all" ? undefined : languagePreset,
      }),
    staleTime: 30_000,
  })

  const rows = useMemo(
    () => (reviewsQuery.data?.data ?? []).map(mapReviewRow),
    [reviewsQuery.data],
  )

  const columns = useMemo(
    () =>
      getReviewColumns({
        expandedReviewId,
        onToggleComment: (reviewId) => {
          setExpandedReviewId((currentId) =>
            currentId === reviewId ? null : reviewId,
          )
        },
      }),
    [expandedReviewId],
  )

  const handleCommentsOnlyChange = (checked: boolean) => {
    startTransition(() => {
      setWithCommentsOnly(checked)
      setExpandedReviewId(null)
      setPageIndex(0)
      if (!checked) {
        setLanguagePreset("all")
      }
    })
  }

  const handleLanguageChange = (value: LanguagePreset) => {
    startTransition(() => {
      setLanguagePreset(value)
      setExpandedReviewId(null)
      setPageIndex(0)
    })
  }

  const emptyText =
    withCommentsOnly || languagePreset !== "all"
      ? "No reviews match the current filters."
      : "No reviews found."

  if (reviewsQuery.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Unable to load reviews</AlertTitle>
        <AlertDescription>
          {extractErrorMessage(reviewsQuery.error)}
        </AlertDescription>
      </Alert>
    )
  }

  return (
    <Card>
      <CardHeader className="gap-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <CardTitle className="text-xl">Reviews</CardTitle>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Label
              htmlFor="dashboard-reviews-comments-only"
              className="flex h-9 items-center gap-3 rounded-md border border-border/70 bg-background/80 px-3 text-sm font-medium text-foreground/90"
            >
              <Switch
                id="dashboard-reviews-comments-only"
                checked={withCommentsOnly}
                onCheckedChange={handleCommentsOnlyChange}
              />
              With comments only
            </Label>
            <Select
              value={languagePreset}
              onValueChange={(value) =>
                handleLanguageChange(value as LanguagePreset)
              }
            >
              <SelectTrigger className="h-9 min-w-44 border-border/70 bg-background/80">
                <SelectValue placeholder="All languages" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All languages</SelectItem>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="zh">Chinese</SelectItem>
                <SelectItem value="ru">Russian</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <DataTable
          columns={columns}
          data={rows}
          isLoading={reviewsQuery.isLoading}
          emptyText={emptyText}
          pageInputEnabled
          getRowId={(row) => row.id}
          serverPagination={{
            pageIndex,
            pageSize,
            totalCount: reviewsQuery.data?.count ?? 0,
            onPageChange: (nextPageIndex) => {
              setExpandedReviewId(null)
              setPageIndex(nextPageIndex)
            },
            onPageSizeChange: (nextPageSize) => {
              startTransition(() => {
                setExpandedReviewId(null)
                setPageIndex(0)
                setPageSize(nextPageSize)
              })
            },
          }}
        />
      </CardContent>
    </Card>
  )
}
