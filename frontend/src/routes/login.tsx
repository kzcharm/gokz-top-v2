import { createFileRoute } from "@tanstack/react-router"
import { useEffect } from "react"

import { redirectToSteamLogin } from "@/lib/auth"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/login")({
  component: Login,
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
