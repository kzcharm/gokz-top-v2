import type { ColumnDef } from "@tanstack/react-table"
import { Star } from "lucide-react"
import { useMemo, useState } from "react"

import type { MapReviewPublic, ReactionSummaryPublic } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { ReactionBar } from "@/components/Reactions/ReactionBar"
import {
  DeleteMapReviewCommentsButton,
  type useMapReviewAdminActions,
} from "@/components/Reviews/admin-actions"
import { cn } from "@/lib/utils"

type MapReviewRow = {
  id: string
  player: MapReviewPublic["player"]
  overall: number
  gameplay: number | null
  visuals: number | null
  comment: string | null
  updatedAt: string
  hasLongComment: boolean
  reactions?: ReactionSummaryPublic
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
  reactions,
}: {
  reviewId: string
  comment: string | null
  isExpanded: boolean
  hasLongComment: boolean
  onToggle: (reviewId: string) => void
  reactions?: ReactionSummaryPublic
}) {
  if (!comment) {
    return <span className="text-sm text-muted-foreground">-</span>
  }

  return (
    <div
      id={`map-review-comment-${reviewId}`}
      className="w-[20rem] max-w-[20rem] space-y-2 whitespace-normal xl:w-[28rem] xl:max-w-[28rem]"
    >
      {hasLongComment ? (
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
      ) : (
        <div className="break-words text-sm leading-6 text-foreground/90">
          {comment}
        </div>
      )}
      <ReactionBar
        targetType="map_review_comment"
        targetId={reviewId}
        reactions={reactions}
      />
    </div>
  )
}

export function MapReviewsTable({
  mapId,
  reviews,
  totalCount,
  isLoading,
  emptyText,
  pageIndex,
  pageSize,
  onPageChange,
  onPageSizeChange,
  deleteCommentsMutation,
}: {
  mapId: number
  reviews: MapReviewPublic[]
  totalCount: number
  isLoading: boolean
  emptyText: string
  pageIndex: number
  pageSize: number
  onPageChange: (pageIndex: number) => void
  onPageSizeChange: (pageSize: number) => void
  deleteCommentsMutation?: ReturnType<
    typeof useMapReviewAdminActions
  >["deleteCommentsMutation"]
}) {
  const [expandedReviewId, setExpandedReviewId] = useState<string | null>(null)

  const rows = useMemo<MapReviewRow[]>(
    () =>
      reviews.map((review) => {
        const comment = review.content.comment?.text?.trim() || null

        return {
          id: review.id,
          player: review.player,
          overall: review.content.overall,
          gameplay: review.content.gameplay ?? null,
          visuals: review.content.visuals ?? null,
          comment,
          updatedAt: review.updated_at,
          hasLongComment:
            comment !== null && comment.length > COMMENT_EXPAND_THRESHOLD,
          reactions: review.reactions,
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
                subline={{
                  type: "wr",
                  mapId,
                  scope: "OVR",
                  recordType: "NUB",
                }}
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
                reactions={row.original.reactions}
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
          ...(deleteCommentsMutation
            ? [
                {
                  id: "actions",
                  header: "",
                  cell: ({ row }) =>
                    row.original.comment ? (
                      <DeleteMapReviewCommentsButton
                        deleteCommentsMutation={deleteCommentsMutation}
                        target={{
                          mapId,
                          steamid64: row.original.player.steamid64,
                          playerName: row.original.player.display_name,
                        }}
                      />
                    ) : null,
                } satisfies ColumnDef<MapReviewRow>,
              ]
            : []),
        ]}
        data={rows}
        isLoading={isLoading}
        emptyText={emptyText}
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
