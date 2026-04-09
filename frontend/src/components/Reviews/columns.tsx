import type { ColumnDef } from "@tanstack/react-table"
import { Star } from "lucide-react"

import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapDisplay } from "@/components/Common/MapDisplay"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { cn } from "@/lib/utils"

export type ReviewTableRow = {
  id: string
  steamid64: string
  map_id: number
  updated_at: string
  player: {
    steamid64: string
    display_name: string
  }
  map: {
    id: number
    name: string
  }
  overall: number
  gameplay: number | null
  visuals: number | null
  comment: string | null
  hasLongComment: boolean
}

type ReviewColumnsOptions = {
  expandedReviewId: string | null
  onToggleComment: (reviewId: string) => void
}

const COMMENT_WIDTH_CLASS = "w-[18rem] max-w-[18rem] xl:w-[22rem] xl:max-w-[22rem]"

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

function CommentPreview({
  reviewId,
  comment,
  hasLongComment,
  isExpanded,
  onToggle,
}: {
  reviewId: string
  comment: string | null
  hasLongComment: boolean
  isExpanded: boolean
  onToggle: (reviewId: string) => void
}) {
  if (!comment) {
    return <span className="text-muted-foreground">-</span>
  }

  if (!hasLongComment) {
    return (
      <div
        className={cn(
          "block whitespace-normal break-words text-sm leading-6 text-foreground/90",
          COMMENT_WIDTH_CLASS,
        )}
      >
        {comment}
      </div>
    )
  }

  return (
    <div
      id={`review-comment-${reviewId}`}
      className={cn("space-y-2 whitespace-normal", COMMENT_WIDTH_CLASS)}
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
        aria-controls={`review-comment-${reviewId}`}
        onClick={() => onToggle(reviewId)}
      >
        {comment}
      </button>
    </div>
  )
}

export function getReviewColumns({
  expandedReviewId,
  onToggleComment,
}: ReviewColumnsOptions): ColumnDef<ReviewTableRow>[] {
  return [
    {
      accessorKey: "map",
      header: "Map",
      cell: ({ row }) => <MapDisplay mapName={row.original.map.name} />,
    },
    {
      accessorKey: "player",
      header: "Player",
      cell: ({ row }) => (
        <PlayerDisplay
          player={{
            steamid64: row.original.player.steamid64,
            displayName: row.original.player.display_name,
          }}
          nameMaxLength={28}
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
        <CommentPreview
          reviewId={row.original.id}
          comment={row.original.comment}
          hasLongComment={row.original.hasLongComment}
          isExpanded={expandedReviewId === row.original.id}
          onToggle={onToggleComment}
        />
      ),
    },
    {
      accessorKey: "updated_at",
      header: "Updated",
      cell: ({ row }) => (
        <div className="whitespace-nowrap">
          <FormattedDateTime
            value={row.original.updated_at}
            display="contextual-relative"
          />
        </div>
      ),
    },
  ]
}
