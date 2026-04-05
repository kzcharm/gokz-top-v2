import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$identifier/")({
  component: ProfileHomeRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Profile"),
      },
    ],
  }),
})

function ProfileHomeRoute() {
  const { identifier } = Route.useParams()
  return <ProfilePage identifier={identifier} activeTab="home" />
}
