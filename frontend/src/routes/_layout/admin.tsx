import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

import { AdminServersService, UsersService } from "@/client"
import { isLoggedIn } from "@/hooks/useAuth"
import { hasRole, isSuperuser } from "@/lib/user-roles"

export const Route = createFileRoute("/_layout/admin")({
  beforeLoad: async ({ location }) => {
    if (location.pathname === "/admin") {
      if (!isLoggedIn()) {
        throw redirect({ to: "/login" })
      }

      const user = await UsersService.readUserMe().catch(() => {
        localStorage.removeItem("access_token")
        throw redirect({ to: "/login" })
      })

      if (isSuperuser(user)) {
        throw redirect({ to: "/admin/users" })
      }
      if (hasRole(user, "map_admin")) {
        throw redirect({ to: "/admin/maps" })
      }

      const hasServerAccess = await AdminServersService.readAdminServerAccess()
        .then(() => true)
        .catch(() => false)

      throw redirect({
        to: hasServerAccess ? "/admin/servers" : "/",
      })
    }
  },
  component: AdminLayout,
})

function AdminLayout() {
  return <Outlet />
}
