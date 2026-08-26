import { createFileRoute } from "@tanstack/react-router"

import { ComparePage } from "@/components/Compare/ComparePage"
import { getPageTitle } from "@/lib/site"

type CompareSearch = {
  player1?: string
  player2?: string
}

export const Route = createFileRoute("/_layout/compare")({
  component: CompareRoute,
  validateSearch: (search: Record<string, unknown>): CompareSearch => ({
    player1: typeof search.player1 === "string" ? search.player1 : undefined,
    player2: typeof search.player2 === "string" ? search.player2 : undefined,
  }),
  head: () => ({
    meta: [{ title: getPageTitle("Compare Players") }],
  }),
})

function CompareRoute() {
  const { player1, player2 } = Route.useSearch()
  return <ComparePage initialPlayer1={player1} initialPlayer2={player2} />
}
