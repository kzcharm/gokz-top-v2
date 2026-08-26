import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$identifier/runs")({
  component: ProfileRunsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Profile Runs"),
      },
    ],
  }),
})

function ProfileRunsRoute() {
  const { identifier } = Route.useParams()
  return <ProfilePage identifier={identifier} activeTab="records" />
}
