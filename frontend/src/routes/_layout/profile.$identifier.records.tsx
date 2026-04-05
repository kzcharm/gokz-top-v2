import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$identifier/records")({
  component: ProfileRecordsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Profile Records"),
      },
    ],
  }),
})

function ProfileRecordsRoute() {
  const { identifier } = Route.useParams()
  return <ProfilePage identifier={identifier} activeTab="records" />
}
