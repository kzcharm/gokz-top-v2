import { createFileRoute } from "@tanstack/react-router"

import { ProfilePage } from "@/components/Profile/ProfilePage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$identifier/maps")({
  component: ProfileMapsRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Profile Maps"),
      },
    ],
  }),
})

function ProfileMapsRoute() {
  const { identifier } = Route.useParams()
  return <ProfilePage identifier={identifier} activeTab="maps" />
}
