import { createFileRoute } from "@tanstack/react-router"

import { MapsLeaderboardTab } from "@/components/Leaderboards/MapsLeaderboardTab"
import { useScope } from "@/components/scope-provider"

export const Route = createFileRoute("/_layout/leaderboards/maps")({
  component: MapsRoute,
})

function MapsRoute() {
  const { scope } = useScope()

  return <MapsLeaderboardTab scope={scope} />
}
