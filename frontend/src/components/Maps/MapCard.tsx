import { Link } from "@tanstack/react-router"
import { Star } from "lucide-react"
import { useTranslation } from "react-i18next"
import type {
  MapLeaderboardEntryPublic,
  MapPublic,
  MapWrPublic,
  RecordPublic,
} from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { MapNameContextMenu } from "@/components/Common/MapDisplay"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import { getRecordModeLabelById } from "@/components/Records/mode"
import { PointsBadge } from "@/components/Records/PointsBadge"
import { formatRecordTime } from "@/components/Records/utils"
import { formatWrGap } from "@/components/Records/wr-gap"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useMapImageUrls } from "@/hooks/useMapImageUrls"
import { formatNumber } from "@/i18n/locale"
import { getMapDownloadUrl } from "@/lib/map-downloads"
import { formatFlooredDecimal } from "@/lib/number-format"
import {
  DEFAULT_MAP_CARD_OPTIONS,
  getFirstMedianWrGap,
  getPersonalSortValue,
  isMapMetric,
  isPersonalSort,
  type MapCardOptions,
} from "./catalog-metrics"
import { MapAuthorsDisplay } from "./MapAuthorsDisplay"
import { MapMetricTooltip } from "./MapMetricTooltip"
import { MapReviewSummary, MapSkillBreakdown } from "./MapOverviewSections"

interface MapCardProps {
  activeTier: number | null
  map: MapPublic
  wrRecord?: MapWrPublic | null
  wrLoading?: boolean
  leaderboardEntry?: MapLeaderboardEntryPublic | null
  sortField?: string
  displayOptions?: MapCardOptions
  showBonusBadge?: boolean
  personalBest?: {
    type: "NUB" | "PRO"
    record?: RecordPublic
    loading: boolean
    error: boolean
    wrTime?: number
  }
}

function formatAveragePlaytime(seconds: number) {
  const minutes = Math.round(seconds / 60)
  return minutes >= 60
    ? `${(minutes / 60).toFixed(1).replace(/\.0$/, "")} h`
    : `${minutes} min`
}

export function MapCard({
  activeTier,
  map,
  wrRecord = null,
  wrLoading = false,
  leaderboardEntry = null,
  sortField = "name",
  displayOptions = DEFAULT_MAP_CARD_OPTIONS,
  showBonusBadge = true,
  personalBest,
}: MapCardProps) {
  const { t } = useTranslation()
  const { formatDateTime } = useDateTimeFormat()
  const imageUrls = useMapImageUrls(map.name, map.workshop_id)
  const downloadUrl = getMapDownloadUrl(map)
  const reviewSummary = map.review_summary
  const bonusCount = map.bonus_count ?? 0
  const leaderboardMetric = leaderboardEntry
    ? (
        {
          playtime: `${Math.round(leaderboardEntry.total_playtime / 3600)} h`,
          avgPlaytime: formatAveragePlaytime(
            leaderboardEntry.average_playtime_per_player,
          ),
          nub: leaderboardEntry.unique_nub_finishes.toLocaleString(),
          pro: leaderboardEntry.unique_pro_finishes.toLocaleString(),
          proRatio: `${(leaderboardEntry.pro_nub_ratio * 100).toFixed(1)}%`,
          finishes: leaderboardEntry.total_finishes.toLocaleString(),
          firstMed: formatRecordTime(
            Math.round(leaderboardEntry.median_first_completion_time),
          ).replace(/\.000$/, ""),
        } as Record<string, string>
      )[sortField]
    : null
  const leaderboardMetricLabel = (
    {
      playtime: "Playtime",
      avgPlaytime: "Avg",
      nub: t("maps.sortOptions.nub"),
      pro: t("maps.sortOptions.pro"),
      proRatio: "PRO Ratio",
      finishes: "Finishes",
      firstMed: "1st Med",
    } as Record<string, string>
  )[sortField]
  const firstMedWrGap = getFirstMedianWrGap(leaderboardEntry, wrRecord?.time)
  const metricValue =
    sortField === "bonus"
      ? formatNumber(bonusCount)
      : sortField === "firstMedWrGap"
        ? firstMedWrGap === null
          ? "—"
          : formatWrGap(firstMedWrGap)
        : leaderboardMetric
  const metricLabel = isMapMetric(sortField)
    ? t(`maps.sortOptions.${sortField}`)
    : leaderboardMetricLabel
  const adjustedRating =
    sortField === "bestRated" ? reviewSummary?.overall_adjusted : undefined
  const personalMetric =
    isPersonalSort(sortField) &&
    sortField !== "pbTime" &&
    sortField !== "pbPoints"
  const personalValue =
    personalMetric && isPersonalSort(sortField)
      ? getPersonalSortValue(
          personalBest?.record,
          sortField,
          personalBest?.wrTime,
        )
      : null
  const personalLabel = personalMetric ? t(`maps.personal.${sortField}`) : ""
  const personalDisplay =
    personalValue === null
      ? "—"
      : sortField === "pbDate"
        ? formatDateTime(personalBest?.record?.created_on ?? "", {
            dateOnly: true,
          })
        : sortField === "pbWrGap"
          ? formatWrGap(personalValue)
          : formatNumber(personalValue, { maximumFractionDigits: 3 })
  const cardMetric =
    adjustedRating === undefined
      ? metricValue
      : formatFlooredDecimal(adjustedRating, 2)

  return (
    <Card
      className="group h-full gap-0 overflow-hidden border-border/70 py-0 transition-all duration-200 hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg"
      data-testid={`map-card-${map.name}`}
    >
      <div className="relative aspect-video overflow-hidden bg-muted">
        <Link
          to="/maps/$mapName/maptop"
          params={{ mapName: map.name }}
          aria-label={`Open ${map.name}`}
          className="block h-full w-full rounded-t-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
        >
          {imageUrls.length > 0 ? (
            <div
              className="absolute inset-0 bg-cover bg-center transition-transform duration-300 group-hover:scale-105"
              style={{
                backgroundImage: imageUrls
                  .map((url) => `url("${url.replace(/"/g, "%22")}")`)
                  .join(", "),
              }}
            />
          ) : null}
          <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-black/35 to-black/85" />
        </Link>

        <div className="absolute inset-x-2 top-2 z-10 flex min-w-0 items-center gap-2">
          <h2 className="flex min-w-0 flex-1 items-center gap-1 select-text text-sm font-semibold text-white">
            <MapNameContextMenu
              mapName={map.name}
              mapId={map.id}
              downloadUrl={downloadUrl}
            >
              {(handlers) => (
                <Link
                  to="/maps/$mapName/maptop"
                  params={{ mapName: map.name }}
                  className="block max-w-full truncate rounded-md bg-black/45 px-2 py-1 whitespace-nowrap"
                  title={map.name}
                  onClick={(event) => {
                    event.stopPropagation()
                  }}
                  onContextMenu={handlers.onContextMenu}
                  onKeyDown={handlers.onKeyDown}
                >
                  {map.name}
                </Link>
              )}
            </MapNameContextMenu>
            <TierBadge
              tier={activeTier}
              className="shrink-0 bg-black/55 text-white backdrop-blur-sm"
            />
          </h2>

          {displayOptions.points &&
          personalBest &&
          (personalBest.record ||
            personalBest.loading ||
            personalBest.error) ? (
            <span
              className="pointer-events-none flex shrink-0 items-center text-xs text-white"
              data-testid={`map-points-${map.id}`}
            >
              {personalBest.record &&
              !personalBest.loading &&
              !personalBest.error ? (
                <PointsBadge
                  points={personalBest.record.points}
                  label={formatFlooredDecimal(personalBest.record.points, 0)}
                />
              ) : personalBest.loading ? (
                "…"
              ) : (
                "—"
              )}
            </span>
          ) : null}
        </div>

        {showBonusBadge && !personalBest && bonusCount > 0 ? (
          <Badge className="pointer-events-none absolute right-2 bottom-2 z-10 border-transparent bg-amber-100/95 font-semibold text-amber-900 shadow-sm ring-1 ring-amber-200 backdrop-blur-sm">
            {t("maps.bonusCount", { count: bonusCount })}
          </Badge>
        ) : null}
        {personalBest ? (
          <span
            className="pointer-events-none absolute bottom-2 right-2 z-10 rounded-md bg-black/75 px-2 py-1 text-xs font-semibold tabular-nums text-white backdrop-blur-sm"
            data-testid={`map-pb-${map.id}`}
          >
            {personalBest.record || personalBest.loading || personalBest.error
              ? "PB: "
              : ""}
            {personalBest.loading
              ? t("maps.personal.loading")
              : personalBest.error
                ? t("maps.personal.unavailable")
                : personalBest.record
                  ? formatRecordTime(
                      personalBest.record.time,
                      displayOptions.milliseconds,
                    )
                  : t("maps.personal.unfinished")}
          </span>
        ) : null}
        {personalMetric && personalBest?.record ? (
          <span className="absolute bottom-2 left-2 z-10 max-w-[52%] truncate rounded-md bg-black/65 px-2 py-1 text-xs font-semibold tabular-nums text-white">
            {personalLabel}: {personalDisplay}
          </span>
        ) : null}
        {cardMetric != null && !personalMetric ? (
          isMapMetric(sortField) ? (
            <div className="absolute bottom-2 left-2 z-10 max-w-[52%]">
              <MapMetricTooltip
                explanation={t(`maps.metricHelp.${sortField}`)}
                label={metricLabel}
              >
                <button
                  type="button"
                  className="truncate rounded-md bg-black/65 px-2 py-1 text-xs font-semibold tabular-nums text-white backdrop-blur-sm"
                  aria-label={`${metricLabel}: ${cardMetric}`}
                >
                  {metricLabel}: {cardMetric}
                </button>
              </MapMetricTooltip>
            </div>
          ) : (
            <Tooltip delayDuration={500}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className="absolute bottom-2 left-2 z-10 flex items-center gap-1 rounded-md bg-black/65 px-2 py-1 text-xs font-semibold tabular-nums text-white backdrop-blur-sm"
                >
                  {t("maps.sortOptions.adjustedRating")} {cardMetric}
                  <Star className="size-3 fill-current" aria-hidden="true" />
                </button>
              </TooltipTrigger>
              <TooltipContent className="max-w-[calc(100vw-1rem)] sm:max-w-sm">
                {t("maps.sortOptions.adjustedRatingTooltip")}
              </TooltipContent>
            </Tooltip>
          )
        ) : null}
      </div>

      {Object.entries(displayOptions).some(
        ([key, value]) => key !== "milliseconds" && key !== "points" && value,
      ) ? (
        <CardContent className="space-y-4 px-5 py-5">
          {displayOptions.wr ? (
            <section
              className="rounded-2xl border border-border/70 bg-muted/30 px-4 py-3"
              aria-label="World record summary"
            >
              {wrRecord ? (
                <div className="flex items-center gap-3">
                  <span className="shrink-0 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    WR
                  </span>
                  <PlayerDisplay
                    player={wrRecord.player}
                    className="min-w-0 flex-1"
                    nameMaxLength={22}
                    subline={{
                      type: "record",
                      mode:
                        getRecordModeLabelById(wrRecord.mode_id) ?? "Unknown",
                      recordType: wrRecord.type,
                      showRecordType: false,
                      time: wrRecord.time,
                      showMilliseconds: displayOptions.milliseconds,
                    }}
                  />
                </div>
              ) : wrLoading ? (
                <div className="text-sm text-muted-foreground">
                  Loading WR...
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">
                  No WR found for this scope.
                </div>
              )}
            </section>
          ) : null}
          {displayOptions.reviews ? (
            <div className="rounded-2xl border border-border/70 bg-muted/40 px-4 py-3">
              <MapReviewSummary map={map} />
            </div>
          ) : null}
          {displayOptions.skills ? (
            <MapSkillBreakdown map={map} compact />
          ) : null}
          {displayOptions.dates ? (
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
          ) : null}
          {displayOptions.authors ? (
            <MapAuthorsDisplay
              authors={map.authors}
              noSteamidNames={map.no_steamid_names}
              compact
              variant="avatar-group"
            />
          ) : null}
        </CardContent>
      ) : null}
    </Card>
  )
}
