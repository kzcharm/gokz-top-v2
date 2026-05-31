import { createFileRoute } from "@tanstack/react-router"

import { CommunityLeaderboardTab } from "@/components/Leaderboards/CommunityLeaderboardTab"

export const Route = createFileRoute("/_layout/leaderboards/community")({
  component: CommunityRoute,
})

function CommunityRoute() {
  return <CommunityLeaderboardTab />
}
