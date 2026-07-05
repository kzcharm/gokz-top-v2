import { createFileRoute, redirect } from "@tanstack/react-router"

import { getSteamid64FromAccessToken } from "@/lib/auth"
import {
  getDefaultPageHref,
  readDefaultPagePreference,
} from "@/lib/default-page"
import { SITE_DEFAULT_DESCRIPTION, SITE_DEFAULT_TITLE } from "@/lib/site"

export const Route = createFileRoute("/_layout/")({
  beforeLoad: () => {
    const accessToken = localStorage.getItem("access_token")
    const steamid64 = getSteamid64FromAccessToken(accessToken)
    const defaultPage = readDefaultPagePreference()

    throw redirect({
      href: getDefaultPageHref(defaultPage, steamid64),
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
