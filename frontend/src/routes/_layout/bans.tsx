import { createFileRoute } from "@tanstack/react-router"

import { BansPage } from "@/components/Bans/BansPage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/bans")({
  component: BansRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Bans"),
      },
    ],
  }),
})

function BansRoute() {
  return <BansPage />
}
