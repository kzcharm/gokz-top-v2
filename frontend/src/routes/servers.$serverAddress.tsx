import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/servers/$serverAddress")({
  component: ServerDetailRoute,
})

function ServerDetailRoute() {
  return null
}
