import { useRouterState } from "@tanstack/react-router"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"

import { getPageTitle } from "@/lib/site"

function getRouteTitleKey(pathname: string) {
  if (pathname === "/login") return "titles.login"
  if (pathname === "/servers") return "titles.servers"
  if (pathname.startsWith("/maps")) return "titles.maps"
  if (pathname.startsWith("/live")) return "titles.live"
  if (pathname.startsWith("/bans")) return "titles.bans"
  if (pathname.startsWith("/leaderboards")) return "titles.leaderboards"
  if (pathname.startsWith("/settings")) return "titles.settings"
  if (pathname.startsWith("/dashboard")) return "titles.dashboard"
  if (pathname.startsWith("/profile") && pathname.endsWith("/records")) {
    return "titles.profileRecords"
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
  if (pathname.startsWith("/admin/servers")) return "titles.adminServers"
  if (pathname.startsWith("/admin/player-sessions")) {
    return "titles.adminPlayerSessions"
  }
  if (pathname.startsWith("/admin/player-social-links")) {
    return "titles.adminPlayerSocialLinks"
  }

  return null
}

export function DocumentTitleSync() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const { t, i18n } = useTranslation()

  useEffect(() => {
    document.documentElement.lang = i18n.resolvedLanguage ?? "en"

    if (pathname.startsWith("/maps/")) {
      const mapName = decodeURIComponent(pathname.split("/maps/")[1] ?? "")
      document.title = getPageTitle(mapName)
      return
    }

    const titleKey = getRouteTitleKey(pathname)
    document.title = getPageTitle(titleKey ? t(titleKey) : undefined)
  }, [i18n.resolvedLanguage, pathname, t])

  return null
}
