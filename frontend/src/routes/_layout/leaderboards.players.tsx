import { createFileRoute } from "@tanstack/react-router"

import { PlayersLeaderboardTab } from "@/components/Leaderboards/PlayersLeaderboardTab"

export const Route = createFileRoute("/_layout/leaderboards/players")({
  component: PlayersRoute,
})

function PlayersRoute() {
  return <PlayersLeaderboardTab />
}
