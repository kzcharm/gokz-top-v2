import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$identifier/friends")({
  component: ProfileFriendsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Profile Friends"),
      },
    ],
  }),
})

function ProfileFriendsRoute() {
  const { identifier } = Route.useParams()
  return <ProfilePage identifier={identifier} activeTab="friends" />
}
