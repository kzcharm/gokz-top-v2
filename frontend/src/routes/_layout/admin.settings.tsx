import { createFileRoute, redirect } from "@tanstack/react-router"
import { UsersService } from "@/client"
import AdminSettings from "@/components/Admin/AdminSettings"
import { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"
import { isSuperuser } from "@/lib/user-roles"

export const Route = createFileRoute("/_layout/admin/settings")({
  component: AdminSettingsRoute,
  beforeLoad: async () => {
    if (!isLoggedIn()) throw redirect({ to: "/login" })
    const user = await UsersService.readUserMe().catch(() => {
      localStorage.removeItem("access_token")
      throw redirect({ to: "/login" })
    })
    if (!isSuperuser(user)) throw redirect({ to: "/" })
  },
  head: () => ({ meta: [{ title: getPageTitle() }] }),
})

function AdminSettingsRoute() {
  return <AdminSettings />
}
