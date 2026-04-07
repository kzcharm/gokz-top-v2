import { createFileRoute, redirect } from "@tanstack/react-router"

import { getSteamid64FromAccessToken } from "@/lib/auth"
import {
  FALLBACK_PROFILE_STEAMID64,
  getFirstSidebarLeafPath,
  getStoredSidebarLayout,
} from "@/components/Sidebar/sidebar-layout"

export const Route = createFileRoute("/_layout/")({
  beforeLoad: () => {
    const accessToken = localStorage.getItem("access_token")
    const steamid64 = getSteamid64FromAccessToken(accessToken)
    const firstSidebarPath = getFirstSidebarLeafPath({
      layout: getStoredSidebarLayout(),
      profileSteamid64: steamid64 ?? FALLBACK_PROFILE_STEAMID64,
    })

    throw redirect({
      href: firstSidebarPath,
    })
  },
  component: IndexRedirect,
})

function IndexRedirect() {
  return null
}
