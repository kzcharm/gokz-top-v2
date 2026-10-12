import { createFileRoute, redirect } from "@tanstack/react-router"
import { useEffect } from "react"

import { isLoggedIn } from "@/hooks/useAuth"
import {
  getSteamid64FromAccessToken,
  getStoredAuthReturnTo,
  redirectToSteamLogin,
} from "@/lib/auth"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/login")({
  component: Login,
  beforeLoad: () => {
    if (isLoggedIn()) {
      const steamid64 = getSteamid64FromAccessToken(
        localStorage.getItem("access_token"),
      )
      throw redirect({
        href: getStoredAuthReturnTo(steamid64 ? `/profile/${steamid64}` : "/"),
        replace: true,
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: getPageTitle(),
      },
    ],
  }),
})

function Login() {
  useEffect(() => {
    redirectToSteamLogin({ replace: true })
  }, [])

  return null
}

export default Login
