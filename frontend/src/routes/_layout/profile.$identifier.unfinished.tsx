import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$identifier/unfinished")(
  {
    component: ProfileUnfinishedRoute,
    head: () => ({
      meta: [
        {
          title: getPageTitle("Profile Unfinished"),
        },
      ],
    }),
  },
)

function ProfileUnfinishedRoute() {
  const { identifier } = Route.useParams()
  return <ProfilePage identifier={identifier} activeTab="unfinished" />
}
