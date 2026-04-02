import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$steamid64/")({
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
  const { steamid64 } = Route.useParams()
  return <ProfilePage steamid64={steamid64} activeTab="home" />
}
