import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/profile/$identifier/comments")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/profile/$identifier",
      params: { identifier: params.identifier },
    })
  },
  component: ProfileCommentsRedirect,
})

function ProfileCommentsRedirect() {
  return null
}
