import { Link } from "@tanstack/react-router"
import { Star } from "lucide-react"

import type { MapPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { getMapImageUrl } from "@/components/Common/MapDisplay"
import { getMapSkillPortions } from "@/components/Maps/map-utils"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface MapCardProps {
  activeTier: number
  map: MapPublic
}

function formatReviewAverage(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "0.0"
  }

  return value.toFixed(1)
}

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

function ReviewSummaryRow({
  label,
  value,
  count,
  suffix,
}: {
  label: string
  value: number | null
  count?: number
  suffix?: string
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-14 text-xs font-medium text-muted-foreground">
        {label}
      </span>
      <ScoreStars value={value} />
      <span className="text-sm font-medium tabular-nums text-foreground">
        {formatReviewAverage(value)}
      </span>
      {count !== undefined ? (
        <span className="text-xs font-medium text-muted-foreground">
          ({count})
        </span>
      ) : null}
      {suffix ? (
        <span className="text-xs font-medium text-muted-foreground">
          {suffix}
        </span>
      ) : null}
    </div>
  )
}

export function MapCard({ activeTier, map }: MapCardProps) {
  const imageUrl = getMapImageUrl(map.name)
  const reviewSummary = map.review_summary
  const reviewsCount = reviewSummary?.reviews_count ?? 0
  const commentsCount = reviewSummary?.comments_count ?? 0
  const allSkillPortions = getMapSkillPortions(map.name)
  const nonZeroSkillPortions = allSkillPortions.filter(
    (portion) => portion.percentage > 0,
  )
  const skillPortions =
    nonZeroSkillPortions.length > 0 && nonZeroSkillPortions.length < 4
      ? allSkillPortions.slice(0, 4)
      : nonZeroSkillPortions.slice(0, 6)

  return (
    <Card
      className="group h-full gap-0 overflow-hidden border-border/70 py-0 transition-all duration-200 hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg"
      data-testid={`map-card-${map.name}`}
    >
      <div className="relative aspect-video overflow-hidden bg-muted">
        <Link
          to="/maps/$mapName"
          params={{ mapName: map.name }}
          aria-label={`Open ${map.name}`}
          className="block h-full w-full rounded-t-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
        >
          {imageUrl ? (
            <div
              className="absolute inset-0 bg-cover bg-center transition-transform duration-300 group-hover:scale-105"
              style={{ backgroundImage: `url(${imageUrl})` }}
            />
          ) : null}
          <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-black/35 to-black/85" />
        </Link>

        <div className="absolute inset-x-4 top-4 flex items-start justify-between gap-3">
          <h2 className="z-10 min-w-0 select-text break-all text-lg font-semibold text-white drop-shadow-sm">
            {map.name}
          </h2>
          <div className="pointer-events-none z-10 shrink-0">
            <TierBadge
              tier={activeTier}
              className="bg-black/55 text-white backdrop-blur-sm"
            />
          </div>
        </div>
      </div>

      <CardContent className="space-y-4 px-5 py-5">
        <section
          className="rounded-2xl border border-border/70 bg-muted/40 px-4 py-3"
          aria-label="Review summary"
        >
          <div className="flex flex-col gap-1 whitespace-normal">
            <ReviewSummaryRow
              label="Overall"
              value={reviewSummary?.overall_avg ?? null}
              suffix={`(${commentsCount} / ${reviewsCount})`}
            />
            <ReviewSummaryRow
              label="Gameplay"
              value={reviewSummary?.gameplay_avg ?? null}
              count={reviewSummary?.gameplay_count ?? 0}
            />
            <ReviewSummaryRow
              label="Visuals"
              value={reviewSummary?.visuals_avg ?? null}
              count={reviewSummary?.visuals_count ?? 0}
            />
          </div>
        </section>

        <section className="space-y-3" aria-label="Skill breakdown">
          <div
            className="flex h-2.5 overflow-hidden rounded-full bg-muted"
            aria-hidden="true"
          >
            {skillPortions.map((portion) => (
              <div
                key={portion.label}
                className="h-full"
                style={{
                  backgroundColor: portion.color,
                  width: `${portion.percentage}%`,
                }}
              />
            ))}
          </div>

          <ul className="grid grid-cols-2 gap-x-4 gap-y-2">
            {skillPortions.map((portion) => (
              <li
                key={portion.label}
                className="flex items-center justify-between gap-2 text-xs"
              >
                <span className="flex min-w-0 items-center gap-2 text-muted-foreground">
                  <span
                    className="size-2 shrink-0 rounded-full"
                    style={{ backgroundColor: portion.color }}
                  />
                  <span className="truncate">{portion.label}</span>
                </span>
                <span className="font-medium tabular-nums text-foreground">
                  {portion.percentage}%
                </span>
              </li>
            ))}
          </ul>
        </section>

        <dl className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <dt className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
              Created
            </dt>
            <dd className="text-sm font-medium text-foreground">
              <FormattedDateTime value={map.created_on} fallback="-" />
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
              Updated
            </dt>
            <dd className="text-sm font-medium text-foreground">
              <FormattedDateTime value={map.updated_on} fallback="-" />
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  )
}
