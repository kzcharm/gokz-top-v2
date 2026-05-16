import { createFileRoute } from "@tanstack/react-router"

import { JumpstatsLeaderboardTab } from "@/components/Leaderboards/JumpstatsLeaderboardTab"
import { useScope } from "@/components/scope-provider"

export const Route = createFileRoute("/_layout/leaderboards/jumpstats")({
  component: JumpstatsRoute,
})

function JumpstatsRoute() {
  const { scope } = useScope()

  return <JumpstatsLeaderboardTab scope={scope} />
}
