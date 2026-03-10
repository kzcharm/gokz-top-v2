import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/admin")({
  beforeLoad: ({ location }) => {
    if (location.pathname === "/admin") {
      throw redirect({
        to: "/admin/users",
      })
    }
  },
  component: AdminLayout,
})

function AdminLayout() {
  return <Outlet />
}
