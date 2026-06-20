import { createFileRoute, redirect } from "@tanstack/react-router"

import { getSteamid64FromAccessToken } from "@/lib/auth"
import { SITE_DEFAULT_DESCRIPTION, SITE_DEFAULT_TITLE } from "@/lib/site"

export const Route = createFileRoute("/_layout/")({
  beforeLoad: () => {
    const accessToken = localStorage.getItem("access_token")
    const steamid64 = getSteamid64FromAccessToken(accessToken)

    if (!steamid64) {
      throw redirect({
        to: "/servers",
      })
    }

    throw redirect({
      to: "/profile/$identifier",
      params: { identifier: steamid64 },
    })
  },
  head: () => ({
    meta: [
      {
        title: SITE_DEFAULT_TITLE,
      },
      {
        name: "description",
        content: SITE_DEFAULT_DESCRIPTION,
      },
    ],
  }),
  component: IndexRedirect,
})

function IndexRedirect() {
  return null
}
