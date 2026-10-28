import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import {
  MeService,
  type PlayerComparisonPublic,
  type RecordPublic,
} from "@/client"
import { CompletionCard } from "@/components/Profile/ProfileCompletionCard"
import {
  buildProfileCompletionData,
  buildProfileTrophyCounts,
  getProfileMapWrsQueryOptions,
  getProfileValidatedMapsQueryOptions,
} from "@/components/Profile/profile-utils"
import { isLoggedIn } from "@/hooks/useAuth"

export function CompareCompletion({
  comparison,
  slot,
}: {
  comparison: PlayerComparisonPublic
  slot: "player1" | "player2"
}) {
  const { t } = useTranslation()
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
    const nubRecords = comparison.nub_runs
      .map((row) => row[slot])
      .filter((record): record is RecordPublic => record != null)
    const proRecords = comparison.pro_runs
      .map((row) => row[slot])
      .filter((record): record is RecordPublic => record != null)
    return {
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
  }, [comparison, slot, maps.data, wrs.data, useWrBasedProCompletion])
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
    <div className="space-y-3" data-testid={`compare-completion-${slot}`}>
      {(["nub", "pro"] as const).map((type) => (
        <CompletionCard
          key={type}
          compact
          title={t(`profile.completion.${type}Title`)}
          {...data.completion[type]}
          trophies={data[type]}
        />
      ))}
    </div>
  )
}
