import { createFileRoute } from "@tanstack/react-router"
import { PlayerCardPage } from "@/components/Profile/PlayerCardPage"
import type { AppScope } from "@/components/scope-provider"
import type { SupportedLocale } from "@/i18n"

export const Route = createFileRoute("/cards/player/$identifier")({
  validateSearch: (
    search: Record<string, unknown>,
  ): { scope: AppScope; lang: SupportedLocale } => ({
    scope: ["OVR", "KZT", "SKZ", "VNL"].includes(String(search.scope))
      ? (search.scope as AppScope)
      : "OVR",
    lang: ["en", "zh-CN", "ru"].includes(String(search.lang))
      ? (search.lang as SupportedLocale)
      : "en",
  }),
  head: () => ({
    meta: [
      { title: "Player card" },
      { name: "robots", content: "noindex, nofollow" },
    ],
  }),
  component: PlayerCardRoute,
})

function PlayerCardRoute() {
  const { identifier } = Route.useParams()
  const { scope, lang } = Route.useSearch()
  return (
    <PlayerCardPage
      key={`${identifier}:${scope}:${lang}`}
      identifier={identifier}
      scope={scope}
      lang={lang}
    />
  )
}
