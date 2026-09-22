import { createFileRoute, redirect } from "@tanstack/react-router"

import { getSteamid64FromAccessToken, getStoredAuthReturnTo } from "@/lib/auth"

export const Route = createFileRoute("/auth/callback")({
  component: AuthCallback,
  beforeLoad: async () => {
    if (typeof window !== "undefined") {
      const hash = window.location.hash
      if (hash) {
        const params = new URLSearchParams(hash.substring(1))
        const accessToken = params.get("access_token")
        if (accessToken) {
          localStorage.setItem("access_token", accessToken)
          const steamid64 = getSteamid64FromAccessToken(accessToken)
          throw redirect({
            href: getStoredAuthReturnTo(
              steamid64 ? `/profile/${steamid64}` : "/",
            ),
            replace: true,
          })
        }
      }
    }
    throw redirect({ to: "/login" })
  },
})

function AuthCallback() {
  return null
}
