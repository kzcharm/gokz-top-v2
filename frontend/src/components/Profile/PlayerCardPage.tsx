import { useQuery } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { PlayersService } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { getPlayerRatingBadgeIcon } from "@/components/Common/player-rating"
import { getScopeTone } from "@/components/Common/ScopeSelector"
import type { AppScope } from "@/components/scope-provider"
import i18n, { type SupportedLocale } from "@/i18n"
import { CompletionCard } from "./ProfileCompletionCard"
import { SkillRadar } from "./ProfileSkillRadar"
import {
  getRatingRankLabel,
  getRatingRankLevel,
  ratingRankBadgeClasses,
} from "./profile-ranks"
import {
  buildProfileCompletionData,
  buildProfileTotalPoints,
  buildProfileTrophyCounts,
  formatNumber,
  formatRating,
  getProfilePbRecordsQueryOptions,
  getProfilePointsStandingQueryOptions,
  getProfileStatsQueryOptions,
  getProfileValidatedMapsQueryOptions,
} from "./profile-utils"
import "./player-card.css"

const copy = {
  en: {
    loading: "Loading player…",
    error: "Unable to load this player card.",
    country: "Unknown country",
  },
  "zh-CN": {
    loading: "正在加载玩家资料…",
    error: "无法加载玩家卡片。",
    country: "未知国家或地区",
  },
  ru: {
    loading: "Загрузка игрока…",
    error: "Не удалось загрузить карточку игрока.",
    country: "Страна неизвестна",
  },
}

export function PlayerCardPage({
  identifier,
  scope,
  lang,
}: {
  identifier: string
  scope: AppScope
  lang: SupportedLocale
}) {
  const { t } = useTranslation()
  const root = useRef<HTMLElement>(null)
  const [languageReady, setLanguageReady] = useState(false)
  const [assetState, setAssetState] = useState<"loading" | "ready" | "error">(
    "loading",
  )
  useEffect(() => {
    let active = true
    void i18n.changeLanguage(lang).then(() => {
      if (active) setLanguageReady(true)
    })
    return () => {
      active = false
    }
  }, [lang])

  const player = useQuery({
    queryKey: ["player-card-identity", identifier],
    queryFn: () =>
      PlayersService.readPlayer({ identifier, refreshSteamProfile: false }),
    retry: false,
  })
  const maps = useQuery({
    ...getProfileValidatedMapsQueryOptions(),
    retry: false,
  })
  const steamid64 = player.data?.steamid64 ?? null
  const nub = useQuery({
    ...getProfilePbRecordsQueryOptions({
      identifier: steamid64,
      scope,
      isProOnly: false,
      isBonus: false,
      stage: 0,
    }),
    enabled: steamid64 !== null,
    retry: false,
  })
  const pro = useQuery({
    ...getProfilePbRecordsQueryOptions({
      identifier: steamid64,
      scope,
      isProOnly: true,
      isBonus: false,
      stage: 0,
    }),
    enabled: steamid64 !== null,
    retry: false,
  })
  const standing = useQuery({
    ...getProfilePointsStandingQueryOptions({ identifier: steamid64, scope }),
    retry: false,
  })
  const stats = useQuery(getProfileStatsQueryOptions(steamid64, "playtime"))
  const longJump = useQuery({
    queryKey: ["player-card-long-jump", steamid64],
    queryFn: () =>
      PlayersService.readPlayerJumpstats({
        identifier: steamid64!,
        type: "LJ",
        limit: 1,
        offset: 0,
        sortBy: "distance",
        sortOrder: "desc",
      }),
    enabled: steamid64 !== null,
    retry: false,
  })
  const queries = [player, maps, nub, pro, standing, stats, longJump]
  const failed = queries.some((query) => query.isError)
  const loaded = languageReady && queries.every((query) => query.isSuccess)

  useEffect(() => {
    if (!loaded || failed) return
    let active = true
    let frame = 0
    const timeout = window.setTimeout(() => {
      if (active) {
        setAssetState("error")
        active = false
        cancelAnimationFrame(frame)
      }
    }, 15_000)
    void document.fonts.ready.then(() => {
      const check = () => {
        if (!active) return
        const images = Array.from(root.current?.querySelectorAll("img") ?? [])
        if (images.every((img) => img.complete && img.naturalWidth > 0)) {
          window.clearTimeout(timeout)
          setAssetState("ready")
        } else frame = requestAnimationFrame(check)
      }
      frame = requestAnimationFrame(check)
    })
    return () => {
      active = false
      window.clearTimeout(timeout)
      cancelAnimationFrame(frame)
    }
  }, [loaded, failed])

  const completion = buildProfileCompletionData({
    maps: maps.data ?? [],
    nubRecords: nub.data ?? [],
    proRecords: [],
    proWrs: [],
    scope,
    useWrBasedProCompletion: false,
  }).nub
  const rating = standing.data?.rating ?? null
  const state = failed ? "error" : loaded ? assetState : "loading"
  let country = copy[lang].country
  if (player.data?.country) {
    try {
      country =
        new Intl.DisplayNames([lang], { type: "region" }).of(
          player.data.country.toUpperCase(),
        ) ?? country
    } catch {
      /* Keep the localized fallback. */
    }
  }

  return (
    <main
      ref={root}
      className="player-card dark"
      data-testid="player-card"
      data-render-state={state}
      data-card-version="1"
      data-scope={scope}
      lang={lang}
    >
      {failed || assetState === "error" ? (
        <p role="alert" className="p-8">
          {copy[lang].error}
        </p>
      ) : !loaded ? (
        <p className="p-8">{copy[lang].loading}</p>
      ) : (
        <>
          <header className="space-y-4 p-5">
            <div className="flex items-start justify-between gap-3">
              <PlayerDisplay
                player={player.data}
                presentation="card"
                disableProfileLink
                showCountryFlag
                subline={{ type: "text", value: country }}
                scope={scope}
                className="min-w-0 flex-1"
              />
              <span
                data-testid="card-scope"
                className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${getScopeTone(scope)}`}
              >
                {scope}
              </span>
            </div>
            <div
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 ${rating === null ? "border-border text-muted-foreground" : ratingRankBadgeClasses[getRatingRankLevel(rating)]}`}
            >
              {rating !== null && (
                <img
                  src={getPlayerRatingBadgeIcon(getRatingRankLevel(rating))}
                  alt={getRatingRankLabel(rating)}
                  className="size-9 object-contain"
                />
              )}
              <span className="text-lg font-semibold">
                {rating === null
                  ? t("profile.unranked")
                  : getRatingRankLabel(rating)}
              </span>
              {rating !== null && (
                <span className="font-mono text-2xl font-semibold">
                  {formatRating(rating)}
                </span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <p className="text-sm text-muted-foreground">
                  {t("profile.summary.global")}
                </p>
                <p className="mt-1 text-xl font-semibold tabular-nums">
                  {standing.data?.rank == null
                    ? t("profile.unranked")
                    : `#${formatNumber(standing.data.rank)}`}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">
                  {standing.data?.region ?? t("profile.summary.regional")}
                </p>
                <p className="mt-1 text-xl font-semibold tabular-nums">
                  {standing.data?.regionalRank == null
                    ? t("profile.unranked")
                    : `#${formatNumber(standing.data.regionalRank)}`}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">
                  {t("labels.points")}
                </p>
                <p className="mt-1 text-xl font-semibold tabular-nums">
                  {formatNumber(
                    buildProfileTotalPoints({
                      nubRecords: nub.data ?? [],
                      proRecords: pro.data ?? [],
                    }),
                  )}
                </p>
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-x-5 gap-y-3 border-t border-border pt-4 text-sm">
              <div>
                <dt className="text-muted-foreground">
                  {t("profile.summary.dateJoined")}
                </dt>
                <dd className="mt-1 font-semibold">
                  <FormattedDateTime
                    value={player.data?.created_at}
                    display="relative"
                    tickerMs={0}
                    fallback="—"
                  />
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">
                  {t("profile.summary.lastPlayed")}
                </dt>
                <dd className="mt-1 font-semibold">
                  <FormattedDateTime
                    value={player.data?.last_played_at}
                    display="relative"
                    tickerMs={0}
                    fallback="—"
                  />
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">
                  {t("profile.summary.playtime")}
                </dt>
                <dd className="mt-1 font-semibold">
                  {new Intl.NumberFormat(lang, {
                    style: "unit",
                    unit: "hour",
                    unitDisplay: "long",
                    maximumFractionDigits: 1,
                  }).format((stats.data?.playtime?.total_seconds ?? 0) / 3600)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">
                  {t("profile.summary.ljPb")}
                </dt>
                <dd className="mt-1 font-semibold">
                  {longJump.data?.data[0]
                    ? `${new Intl.NumberFormat(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(longJump.data.data[0].distance)} ${t("profile.jumpstats.units")}`
                    : "—"}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-muted-foreground">
                  {t("profile.summary.favoriteServer")}
                </dt>
                <dd className="mt-1 break-words font-semibold">
                  {player.data?.favorite_server?.label ?? "—"}
                </dd>
              </div>
            </dl>
          </header>
          <section
            className="border-t border-border"
            aria-label="NUB completion"
          >
            <CompletionCard
              card
              title={t("profile.completion.nubTitle")}
              completed={completion.completed}
              total={completion.total}
              tiers={completion.tiers}
              trophies={buildProfileTrophyCounts(nub.data ?? [])}
            />
          </section>
          <section
            className="border-t border-border px-6 py-4"
            aria-label={t("profile.skillRadar.relativeAriaLabel")}
          >
            <SkillRadar card ratings={standing.data?.skillRatings ?? null} />
          </section>
        </>
      )}
    </main>
  )
}
