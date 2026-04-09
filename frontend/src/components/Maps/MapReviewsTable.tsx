import { Star } from "lucide-react"
import { useMemo, useState } from "react"

import type { MapReviewPublic } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { cn } from "@/lib/utils"

type MapReviewRow = {
  id: string
  player: MapReviewPublic["player"]
  overall: number
  gameplay: number | null
  visuals: number | null
  comment: string
  updatedAt: string
  hasLongComment: boolean
}

const COMMENT_EXPAND_THRESHOLD = 180

function ScoreStars({ value }: { value: number | null }) {
  const filledStars = value ?? 0

  return (
    <div
      className="flex min-w-[6.25rem] items-center gap-0.5"
      role="img"
      aria-label={
        value === null
          ? "No rating provided, 0 out of 5 stars"
          : `${value} out of 5 stars`
      }
    >
      {Array.from({ length: 5 }, (_, index) => (
        <Star
          key={index}
          className={cn(
            "size-3.5",
            index < filledStars
              ? "fill-amber-400 text-amber-400"
              : "fill-transparent text-muted-foreground/35",
          )}
        />
      ))}
    </div>
  )
}

function RatingsStack({
  overall,
  gameplay,
  visuals,
}: {
  overall: number
  gameplay: number | null
  visuals: number | null
}) {
  return (
    <div className="flex min-w-[8.5rem] flex-col gap-1 whitespace-normal">
      <div className="flex items-center gap-2">
        <span className="w-14 text-xs font-medium text-muted-foreground">
          Overall
        </span>
        <ScoreStars value={overall} />
      </div>
      <div className="flex items-center gap-2">
        <span className="w-14 text-xs font-medium text-muted-foreground">
          Gameplay
        </span>
        <ScoreStars value={gameplay} />
      </div>
      <div className="flex items-center gap-2">
        <span className="w-14 text-xs font-medium text-muted-foreground">
          Visuals
        </span>
        <ScoreStars value={visuals} />
      </div>
    </div>
  )
}

function CommentCell({
  reviewId,
  comment,
  isExpanded,
  hasLongComment,
  onToggle,
}: {
  reviewId: string
  comment: string
  isExpanded: boolean
  hasLongComment: boolean
  onToggle: (reviewId: string) => void
}) {
  if (!hasLongComment) {
    return (
      <div className="w-[20rem] max-w-[20rem] whitespace-normal break-words text-sm leading-6 text-foreground/90 xl:w-[28rem] xl:max-w-[28rem]">
        {comment}
      </div>
    )
  }

  return (
    <div
      id={`map-review-comment-${reviewId}`}
      className="w-[20rem] max-w-[20rem] whitespace-normal xl:w-[28rem] xl:max-w-[28rem]"
    >
      <button
        type="button"
        className={cn(
          "block w-full cursor-pointer overflow-hidden text-left text-sm leading-6 text-foreground/90 underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          isExpanded
            ? "whitespace-pre-wrap break-words hover:text-foreground"
            : "line-clamp-3 whitespace-normal break-words hover:text-foreground hover:underline",
        )}
        title={isExpanded ? undefined : comment}
        aria-expanded={isExpanded}
        aria-controls={`map-review-comment-${reviewId}`}
        onClick={() => onToggle(reviewId)}
      >
        {comment}
      </button>
    </div>
  )
}

export function MapReviewsTable({
  reviews,
  totalCount,
  isLoading,
  pageIndex,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: {
  reviews: MapReviewPublic[]
  totalCount: number
  isLoading: boolean
  pageIndex: number
  pageSize: number
  onPageChange: (pageIndex: number) => void
  onPageSizeChange: (pageSize: number) => void
}) {
  const [expandedReviewId, setExpandedReviewId] = useState<string | null>(null)

  const rows = useMemo<MapReviewRow[]>(
    () =>
      reviews
        .filter((review) => {
          const comment = review.content.comment?.text?.trim()
          return Boolean(comment)
        })
        .map((review) => {
          const comment = review.content.comment?.text?.trim() ?? ""

          return {
            id: `${review.steamid64}-${review.map_id}`,
            player: review.player,
            overall: review.content.overall,
            gameplay: review.content.gameplay ?? null,
            visuals: review.content.visuals ?? null,
            comment,
            updatedAt: review.updated_at,
            hasLongComment: comment.length > COMMENT_EXPAND_THRESHOLD,
          }
        }),
    [reviews],
  )

  return (
    <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm [&_[data-slot=table-container]]:border-0 [&_[data-slot=table-container]]:bg-card">
      <DataTable
        columns={[
          {
            accessorKey: "player",
            header: "Player",
            cell: ({ row }) => (
              <PlayerDisplay
                player={row.original.player}
                className="max-w-[15rem]"
                nameMaxLength={24}
              />
            ),
          },
          {
            id: "ratings",
            header: "Ratings",
            cell: ({ row }) => (
              <RatingsStack
                overall={row.original.overall}
                gameplay={row.original.gameplay}
                visuals={row.original.visuals}
              />
            ),
          },
          {
            accessorKey: "comment",
            header: "Comment",
            cell: ({ row }) => (
              <CommentCell
                reviewId={row.original.id}
                comment={row.original.comment}
                isExpanded={expandedReviewId === row.original.id}
                hasLongComment={row.original.hasLongComment}
                onToggle={(reviewId) => {
                  setExpandedReviewId((currentId) =>
                    currentId === reviewId ? null : reviewId,
                  )
                }}
              />
            ),
          },
          {
            accessorKey: "updatedAt",
            header: "Updated",
            cell: ({ row }) => (
              <div className="whitespace-nowrap text-sm text-muted-foreground">
                <FormattedDateTime
                  value={row.original.updatedAt}
                  display="contextual-relative"
                />
              </div>
            ),
          },
        ]}
        data={rows}
        isLoading={isLoading}
        emptyText="No map reviews with comments yet."
        getRowId={(row) => row.id}
        pageInputEnabled
        serverPagination={{
          pageIndex,
          pageSize,
          totalCount,
          onPageChange,
          onPageSizeChange,
        }}
      />
    </div>
  )
}
