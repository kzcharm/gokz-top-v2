import { createFileRoute } from "@tanstack/react-router"

import { RecentWrsPanel } from "@/components/Records/RecentWrsPanel"

export const Route = createFileRoute("/_layout/dashboard/wrs")({
  component: DashboardWrs,
})

function DashboardWrs() {
  return <RecentWrsPanel />
}
