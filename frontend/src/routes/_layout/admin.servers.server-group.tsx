import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/admin/servers/server-group")({
  component: EmptyAdminServersChildRoute,
})

function EmptyAdminServersChildRoute() {
  return null
}
