import { createFileRoute } from "@tanstack/react-router"

import { RecentRecordsPanel } from "@/components/Records/RecentRecordsPanel"

export const Route = createFileRoute("/_layout/dashboard/records")({
  component: DashboardRecords,
})

function DashboardRecords() {
  return <RecentRecordsPanel />
}
