import { Star } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { MapPublic } from "@/client"
import { formatNumber } from "@/i18n/locale"
import { formatFlooredDecimal } from "@/lib/number-format"
import { getMapSkillPortions } from "./map-utils"

function formatReviewAverage(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—"
  }

  return formatFlooredDecimal(value, 1)
}

function ScoreStars({ value }: { value: number | null }) {
  const { t } = useTranslation()
  const filledStars = value ?? 0

  return (
    <div
      className="flex min-w-[6.25rem] items-center gap-0.5"
      role="img"
      aria-label={
        value === null
          ? t("reviews.noRatingAria")
          : t("reviews.ratingAria", { count: value })
      }
    >
      {Array.from({ length: 5 }, (_, index) => (
        <span key={index} className="relative size-3.5" aria-hidden="true">
          <Star className="size-3.5 text-muted-foreground/35" />
          <span
            className="absolute inset-y-0 left-0 overflow-hidden"
            style={{
              width: `${Math.max(0, Math.min(1, filledStars - index)) * 100}%`,
            }}
          >
            <Star className="size-3.5 fill-amber-400 text-amber-400" />
          </span>
        </span>
      ))}
    </div>
  )
}

function ReviewSummaryRow({
  label,
  value,
  count,
}: {
  label: string
  value: number | null
  count?: number
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
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
    </div>
  )
}

export function MapReviewSummary({ map }: { map: MapPublic }) {
  const { t } = useTranslation()
  const summary = map.review_summary
  return (
    <section
      className="flex min-w-0 flex-col gap-2"
      aria-label={t("maps.overview.reviewSummary")}
    >
      {summary && summary.reviews_count > 0 ? (
        <div className="flex flex-col gap-1">
          <ReviewSummaryRow
            label={t("maps.sortOptions.overall")}
            value={summary.overall_avg}
            count={summary.reviews_count}
          />
          <ReviewSummaryRow
            label={t("maps.sortOptions.gameplay")}
            value={summary.gameplay_avg ?? null}
            count={summary.gameplay_count}
          />
          <ReviewSummaryRow
            label={t("maps.sortOptions.visuals")}
            value={summary.visuals_avg ?? null}
            count={summary.visuals_count}
          />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          {t("maps.overview.noReviews")}
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        {t("maps.overview.reviewCounts", {
          reviews: t("maps.overview.ratingCount", {
            count: summary?.reviews_count ?? 0,
            formatted: formatNumber(summary?.reviews_count ?? 0),
          }),
          comments: t("maps.overview.commentCount", {
            count: summary?.comments_count ?? 0,
            formatted: formatNumber(summary?.comments_count ?? 0),
          }),
        })}
      </p>
    </section>
  )
}

export function MapSkillBreakdown({
  map,
  compact = false,
}: {
  map: MapPublic
  compact?: boolean
}) {
  const { t } = useTranslation()
  const allPortions = getMapSkillPortions(map)
  const nonZero = allPortions.filter((portion) => portion.percentage > 0)
  const portions = compact
    ? nonZero.length > 0 && nonZero.length < 4
      ? allPortions.slice(0, 4)
      : nonZero.slice(0, 4)
    : nonZero.slice(0, 6)
  return (
    <section
      className="flex min-w-0 flex-col gap-3"
      aria-label={t("maps.options.skills")}
    >
      <div
        className="flex h-2.5 overflow-hidden rounded-full bg-muted"
        aria-hidden="true"
      >
        {allPortions.map((portion) => (
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
        {portions.map((portion) => (
          <li
            key={portion.label}
            className="flex min-w-0 items-center justify-between gap-2 text-xs"
          >
            <span className="flex min-w-0 items-center gap-2 text-muted-foreground">
              <span
                className="size-2 shrink-0 rounded-full"
                style={{ backgroundColor: portion.color }}
              />
              <span className="truncate">
                {t(`maps.overview.skills.${portion.key}`)}
              </span>
            </span>
            <span className="font-medium tabular-nums text-foreground">
              {formatNumber(portion.percentage)}%
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
