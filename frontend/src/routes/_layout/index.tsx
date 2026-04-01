import { createFileRoute, redirect } from "@tanstack/react-router"

import { UsersService } from "@/client"

export const Route = createFileRoute("/_layout/")({
  beforeLoad: async () => {
    const fallbackSteamid64 = "76561198417871586"
    const accessToken = localStorage.getItem("access_token")

    if (!accessToken) {
      throw redirect({
        to: "/profile/$steamid64",
        params: { steamid64: fallbackSteamid64 },
      })
    }

    try {
      const currentUser = await UsersService.readUserMe()
      throw redirect({
        to: "/profile/$steamid64",
        params: { steamid64: currentUser.steamid64 },
      })
    } catch {
      localStorage.removeItem("access_token")
      throw redirect({
        to: "/profile/$steamid64",
        params: { steamid64: fallbackSteamid64 },
      })
    }
  },
  component: IndexRedirect,
})

function IndexRedirect() {
  return null
}
