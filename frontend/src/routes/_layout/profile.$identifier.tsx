import { createFileRoute, Outlet } from "@tanstack/react-router"

import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/profile/$identifier")({
  component: ProfileLayoutRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Profile"),
      },
    ],
  }),
})

function ProfileLayoutRoute() {
  return <Outlet />
}
