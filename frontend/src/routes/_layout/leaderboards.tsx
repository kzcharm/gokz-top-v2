import { createFileRoute } from "@tanstack/react-router"

import { FeaturePlaceholder } from "@/components/Common/FeaturePlaceholder"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/leaderboards")({
  component: LeaderboardsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Leaderboards"),
      },
    ],
  }),
})

function LeaderboardsRoute() {
  return (
    <FeaturePlaceholder
      section="Leaderboards"
      title="Leaderboards"
      description="Leaderboard views are not implemented yet. This placeholder keeps the sidebar structure in place until the competitive ranking pages are built."
      backTo="/servers"
      backLabel="Go to servers"
    />
  )
}
