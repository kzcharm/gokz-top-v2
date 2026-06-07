import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/servers/group/$customId")({
  component: ServerGroupRoute,
})

function ServerGroupRoute() {
  return null
}
