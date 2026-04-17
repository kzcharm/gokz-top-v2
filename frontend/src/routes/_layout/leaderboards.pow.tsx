import { createFileRoute } from "@tanstack/react-router"

import { PlayersLeaderboardTab } from "@/components/Leaderboards/PlayersLeaderboardTab"

export const Route = createFileRoute("/_layout/leaderboards/pow")({
  component: PowRoute,
})

function PowRoute() {
  return <PlayersLeaderboardTab />
}
