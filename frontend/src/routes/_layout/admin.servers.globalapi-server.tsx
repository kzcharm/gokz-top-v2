import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/admin/servers/globalapi-server")(
  {
    component: EmptyAdminServersChildRoute,
  },
)

function EmptyAdminServersChildRoute() {
  return null
}
