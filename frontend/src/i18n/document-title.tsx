import { useRouterState } from "@tanstack/react-router"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"

import { getPageTitle } from "@/lib/site"

function getRouteTitleKey(pathname: string) {
  if (pathname === "/login") return "titles.login"
  if (pathname.startsWith("/servers")) return "titles.servers"
  if (pathname.startsWith("/notifications")) return "titles.notifications"
  if (pathname.startsWith("/polls")) return "titles.polls"
  if (pathname.startsWith("/updates")) return "updates.title"
  if (pathname.startsWith("/compare")) return "compare.title"
  if (pathname.startsWith("/maps")) return "titles.maps"
  if (pathname.startsWith("/live")) return "titles.live"
  if (pathname.startsWith("/media")) return "titles.media"
  if (pathname.startsWith("/bans")) return "titles.bans"
  if (pathname.startsWith("/leaderboards")) return "titles.leaderboards"
  if (pathname.startsWith("/settings")) return "titles.settings"
  if (pathname.startsWith("/dashboard")) return "titles.dashboard"
  if (pathname.startsWith("/profile") && pathname.endsWith("/runs")) {
    return "titles.profileRuns"
  }
  if (pathname.startsWith("/profile") && pathname.endsWith("/stats")) {
    return "titles.profileStats"
  }
  if (pathname.startsWith("/profile") && pathname.endsWith("/unfinished")) {
    return "titles.profileUnfinished"
  }
  if (pathname.startsWith("/profile")) return "titles.profile"
  if (pathname.startsWith("/admin/maps")) return "titles.adminMaps"
  if (pathname.startsWith("/admin/players")) return "titles.adminPlayers"
  if (pathname.startsWith("/admin/users")) return "titles.adminUsers"
  if (pathname.startsWith("/admin/settings")) return "titles.adminSettings"
  if (pathname.startsWith("/admin/servers")) return "titles.adminServers"
  if (pathname.startsWith("/admin/player-sessions")) {
    return "titles.adminPlayerSessions"
  }
  if (pathname.startsWith("/admin/player-social-links")) {
    return "titles.adminPlayerSocialLinks"
  }

  return null
}

export function useCurrentPageTitle() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const { t } = useTranslation()

  if (pathname.startsWith("/maps/")) {
    return decodeURIComponent(pathname.split("/maps/")[1] ?? "")
  }

  const titleKey = getRouteTitleKey(pathname)
  return titleKey ? t(titleKey) : undefined
}

export function DocumentTitleSync() {
  const pageTitle = useCurrentPageTitle()
  const { i18n } = useTranslation()

  useEffect(() => {
    document.documentElement.lang = i18n.resolvedLanguage ?? "en"

    document.title = getPageTitle(pageTitle)
  }, [i18n.resolvedLanguage, pageTitle])

  return null
}
