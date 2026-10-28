import { useQuery } from "@tanstack/react-query"
import { CheckCircle2 } from "lucide-react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  MeService,
  type PlayerComparisonPublic,
  type RecordPublic,
} from "@/client"
import { RecordTypeToggle } from "@/components/Common/RecordTypeToggle"
import { TROPHY_ASSETS } from "@/components/Common/trophy-assets"
import {
  buildProfileCompletionData,
  buildProfileTrophyCounts,
  getProfileMapWrsQueryOptions,
  getProfileValidatedMapsQueryOptions,
} from "@/components/Profile/profile-utils"
import { Card, CardContent } from "@/components/ui/card"
import { isLoggedIn } from "@/hooks/useAuth"
import { cn } from "@/lib/utils"
import { COMPARE_PLAYERS, type CompareHighlightProps } from "./compare-player"

export function CompareCompletion({
  comparison,
  activePlayer,
  onHighlightPlayer,
}: {
  comparison: PlayerComparisonPublic
} & CompareHighlightProps) {
  const { t } = useTranslation()
  const [type, setType] = useState<"nub" | "pro">("nub")
  const maps = useQuery(getProfileValidatedMapsQueryOptions())
  const settings = useQuery({
    queryKey: ["player-settings"],
    queryFn: () => MeService.readCurrentPlayerSettings(),
    enabled: isLoggedIn(),
    staleTime: 60_000,
  })
  const useWrBasedProCompletion =
    settings.data?.use_wr_based_pro_completion ?? true
  const wrs = useQuery({
    ...getProfileMapWrsQueryOptions({
      scope: comparison.scope,
      isProOnly: true,
    }),
    enabled: useWrBasedProCompletion,
  })
  const data = useMemo(() => {
    return COMPARE_PLAYERS.map((slot) => {
      const nubRecords = comparison.nub_runs
        .map((row) => row[slot])
        .filter((record): record is RecordPublic => record != null)
      const proRecords = comparison.pro_runs
        .map((row) => row[slot])
        .filter((record): record is RecordPublic => record != null)
      return {
        slot,
        completion: buildProfileCompletionData({
          maps: maps.data ?? [],
          nubRecords,
          proRecords,
          proWrs: wrs.data ?? [],
          scope: comparison.scope,
          useWrBasedProCompletion,
        }),
        nub: buildProfileTrophyCounts(nubRecords),
        pro: buildProfileTrophyCounts(proRecords),
      }
    })
  }, [comparison, maps.data, wrs.data, useWrBasedProCompletion])
  if (maps.isError || (useWrBasedProCompletion && wrs.isError))
    return (
      <p role="alert" className="text-sm text-destructive">
        {t("profile.completion.loadFailedBody")}
      </p>
    )
  if (maps.isLoading || (useWrBasedProCompletion && wrs.isLoading))
    return (
      <p className="text-sm text-muted-foreground">{t("compare.loading")}</p>
    )
  return (
    <Card
      data-testid="compare-completion"
      className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0"
    >
      <CardContent className="space-y-5 p-3 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            {t(`profile.completion.${type}Title`)}
          </h3>
          <RecordTypeToggle
            id="compare-completion-type"
            isProOnly={type === "pro"}
            onCheckedChange={(checked) => setType(checked ? "pro" : "nub")}
            ariaLabel={t("compare.completionType")}
          />
        </div>
        <div className="grid grid-cols-2 gap-4 sm:gap-8">
          {data.map(({ slot, completion, ...trophies }) => (
            <div
              key={slot}
              data-compare-player={slot}
              className={cn(
                "flex min-w-0 flex-wrap items-end justify-between gap-3 transition-opacity",
                activePlayer && activePlayer !== slot && "opacity-30",
              )}
              onPointerEnter={() => onHighlightPlayer(slot)}
              onPointerLeave={() => onHighlightPlayer(null)}
            >
              <div className="flex flex-wrap items-center gap-4">
                {(["gold", "silver", "bronze"] as const).map((trophy) => (
                  <span
                    key={trophy}
                    className="flex items-center gap-2 text-2xl font-semibold tracking-tight"
                  >
                    <img
                      src={TROPHY_ASSETS[trophy]}
                      alt={t("profile.completion.trophyAlt", {
                        trophy: t(`profile.completion.trophies.${trophy}`),
                      })}
                      className="h-7 w-7 object-contain"
                    />
                    {trophies[type][trophy]}
                  </span>
                ))}
              </div>
              <p className="ml-auto whitespace-nowrap text-sm text-muted-foreground">
                {completion[type].completed} / {completion[type].total}
              </p>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-x-3 sm:gap-x-6">
          {data.map(({ slot, completion }, playerIndex) => (
            <div
              key={slot}
              data-compare-player={slot}
              className={cn(
                "grid min-w-0 items-center gap-x-1.5 gap-y-1.5 transition-opacity sm:gap-x-3",
                "grid-cols-[max-content_minmax(0,1fr)_max-content]",
                activePlayer && activePlayer !== slot && "opacity-30",
              )}
              onPointerEnter={() => onHighlightPlayer(slot)}
              onPointerLeave={() => onHighlightPlayer(null)}
            >
              {completion[type].tiers.map((value, index) => (
                <div
                  key={value.label}
                  data-completion-tier=""
                  className="col-span-3 grid grid-cols-subgrid items-center"
                >
                  <span
                    data-completion-tier-label=""
                    className={cn(
                      "row-start-1 whitespace-nowrap text-[11px] font-semibold leading-4 text-muted-foreground sm:text-xs",
                      playerIndex === 0
                        ? "col-start-3 text-right"
                        : "col-start-1 text-left",
                    )}
                  >
                    {value.label} ({t("profile.completion.averageShort")}{" "}
                    <span className="font-mono tabular-nums">
                      {String(value.averagePoints).padStart(3, "0")}
                    </span>
                    )
                  </span>
                  <div
                    role="progressbar"
                    aria-label={`${comparison[slot].player.display_name}: ${type.toUpperCase()} ${value.label}`}
                    aria-valuemin={0}
                    aria-valuemax={Math.max(1, value.total)}
                    aria-valuenow={value.complete}
                    aria-valuetext={`${value.complete}/${value.total}, ${t("profile.completion.averageShort")} ${value.averagePoints}`}
                    className="col-start-2 row-start-1 h-5 overflow-hidden rounded-full bg-muted"
                    data-testid={`compare-track-${slot}-${index + 1}`}
                  >
                    <div
                      className={cn(
                        "h-full rounded-full",
                        playerIndex === 0 && "ml-auto",
                      )}
                      style={{
                        width: `${value.total ? (value.complete / value.total) * 100 : 0}%`,
                        backgroundColor: value.color,
                      }}
                    />
                  </div>
                  <span
                    data-completion-tier-count=""
                    className={cn(
                      "row-start-1 flex items-center gap-1 font-mono text-[11px] text-muted-foreground tabular-nums sm:text-xs",
                      playerIndex === 0
                        ? "col-start-1 justify-end"
                        : "col-start-3 justify-start",
                    )}
                  >
                    {value.complete}/{value.total}
                    {value.total > 0 && value.complete >= value.total ? (
                      <CheckCircle2
                        aria-hidden="true"
                        className="hidden size-3 shrink-0 sm:block"
                        style={{ color: "#22C55E" }}
                      />
                    ) : null}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
