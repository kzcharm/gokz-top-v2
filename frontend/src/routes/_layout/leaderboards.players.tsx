import { createFileRoute } from "@tanstack/react-router"

import { PlayersLeaderboardTab } from "@/components/Leaderboards/PlayersLeaderboardTab"

export const Route = createFileRoute("/_layout/leaderboards/players")({
  component: PlayersRoute,
  validateSearch: (
    search: Record<string, unknown>,
  ): { player?: string; region?: string } => ({
    player:
      typeof search.player === "string" && /^\d{17}$/.test(search.player)
        ? search.player
        : undefined,
    region:
      typeof search.region === "string" && /^[A-Z]{2}$/.test(search.region)
        ? search.region
        : undefined,
  }),
})

function PlayersRoute() {
  const { player, region } = Route.useSearch()
  return (
    <PlayersLeaderboardTab
      key={`${player ?? ""}:${region ?? ""}`}
      targetPlayer={player}
      initialRegion={region}
    />
  )
}
