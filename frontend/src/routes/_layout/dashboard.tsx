import { createFileRoute, Link, Outlet, redirect } from "@tanstack/react-router"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/dashboard")({
  beforeLoad: ({ location }) => {
    if (location.pathname === "/dashboard") {
      throw redirect({
        to: "/dashboard/records",
      })
    }
  },
  component: DashboardLayout,
  head: () => ({
    meta: [
      {
        title: getPageTitle(),
      },
    ],
  }),
})

function DashboardLayout() {
  return (
    <Tabs value="records" className="flex flex-col gap-4">
      <TabsList className="w-fit">
        <TabsTrigger value="records" asChild>
          <Link to="/dashboard/records">Records</Link>
        </TabsTrigger>
      </TabsList>
      <Outlet />
    </Tabs>
  )
}
