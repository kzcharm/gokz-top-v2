import { createFileRoute } from "@tanstack/react-router"

import { BansPage } from "@/components/Bans/BansPage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/bans")({
  component: BansRoute,
  validateSearch: (search: Record<string, unknown>) => ({
    q: typeof search.q === "string" ? search.q : undefined,
  }),
  head: () => ({
    meta: [
      {
        title: getPageTitle("Bans"),
      },
    ],
  }),
})

function BansRoute() {
  const { q } = Route.useSearch()

  return <BansPage initialSearchQuery={q ?? ""} />
}
