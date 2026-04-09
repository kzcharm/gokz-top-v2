import { createFileRoute } from "@tanstack/react-router"

import { ReviewsDashboardPanel } from "@/components/Reviews/ReviewsDashboardPanel"

export const Route = createFileRoute("/_layout/dashboard/reviews")({
  component: DashboardReviews,
})

function DashboardReviews() {
  return <ReviewsDashboardPanel />
}
