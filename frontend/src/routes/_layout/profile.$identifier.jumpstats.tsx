import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$identifier/jumpstats")({
  component: ProfileJumpstatsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Profile Jumpstats"),
      },
    ],
  }),
})

function ProfileJumpstatsRoute() {
  const { identifier } = Route.useParams()
  return <ProfilePage identifier={identifier} activeTab="jumpstats" />
}
