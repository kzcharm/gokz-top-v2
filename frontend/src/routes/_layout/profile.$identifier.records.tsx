import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/profile/$identifier/records")({
  beforeLoad: ({ params, location }) => {
    throw redirect({
      to: "/profile/$identifier/runs",
      params: { identifier: params.identifier },
      search: location.search,
    })
  },
  component: ProfileRecordsRedirect,
})

function ProfileRecordsRedirect() {
  return null
}
