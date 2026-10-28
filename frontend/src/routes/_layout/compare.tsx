import { createFileRoute, useRouter } from "@tanstack/react-router"
import { useEffect } from "react"
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
  const router = useRouter()
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (
      ["player1", "player2"].some((key) =>
        /^"\d{17}"$/.test(params.get(key) ?? ""),
      )
    ) {
      if (player1) params.set("player1", player1)
      if (player2) params.set("player2", player2)
      router.history.replace(
        `${window.location.pathname}?${params}${window.location.hash}`,
        router.state.location.state,
      )
    }
  }, [router, player1, player2])
  return <ComparePage initialPlayer1={player1} initialPlayer2={player2} />
}
