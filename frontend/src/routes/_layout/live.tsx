import { createFileRoute } from "@tanstack/react-router"

import { LivePage } from "@/components/Live/LivePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/live")({
  component: LiveRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Live"),
      },
    ],
  }),
})

function LiveRoute() {
  return <LivePage />
}
