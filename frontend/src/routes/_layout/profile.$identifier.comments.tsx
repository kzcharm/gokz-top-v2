import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$identifier/comments")({
  component: ProfileCommentsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Profile Comments"),
      },
    ],
  }),
})

function ProfileCommentsRoute() {
  const { identifier } = Route.useParams()
  return <ProfilePage identifier={identifier} activeTab="comments" />
}
