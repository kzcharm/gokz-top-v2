import { createFileRoute, redirect } from "@tanstack/react-router"

import { getSteamid64FromAccessToken } from "@/lib/auth"

export const Route = createFileRoute("/_layout/")({
  beforeLoad: () => {
    const fallbackSteamid64 = "76561198417871586"
    const accessToken = localStorage.getItem("access_token")
    const steamid64 = getSteamid64FromAccessToken(accessToken)

    throw redirect({
      to: "/profile/$steamid64",
      params: { steamid64: steamid64 ?? fallbackSteamid64 },
    })
  },
  component: IndexRedirect,
})

function IndexRedirect() {
  return null
}
