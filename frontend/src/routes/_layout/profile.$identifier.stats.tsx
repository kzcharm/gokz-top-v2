import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$identifier/stats")({
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
  const { identifier } = Route.useParams()
  return <ProfilePage identifier={identifier} activeTab="stats" />
}
