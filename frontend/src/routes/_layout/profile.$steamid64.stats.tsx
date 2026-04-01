import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$steamid64/stats")({
  component: ProfileStatsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Profile Stats"),
      },
    ],
  }),
})

function ProfileStatsRoute() {
  const { steamid64 } = Route.useParams()
  return <ProfilePage steamid64={steamid64} activeTab="stats" />
}
