import { createFileRoute } from "@tanstack/react-router"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/servers/group/$customId")({
  component: ServerGroupRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Server Group"),
      },
    ],
  }),
})

function ServerGroupRoute() {
  return null
}
