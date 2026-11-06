import { createFileRoute, redirect } from "@tanstack/react-router"

import { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/notifications")({
  beforeLoad: () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }

    throw redirect({
      to: "/settings/notifications",
    })
  },
  head: () => ({
    meta: [
      {
        title: getPageTitle("Notifications"),
      },
    ],
  }),
})
