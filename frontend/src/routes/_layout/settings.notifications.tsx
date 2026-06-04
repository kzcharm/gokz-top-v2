import { createFileRoute } from "@tanstack/react-router"

import { NotificationsRoute } from "@/routes/_layout/notifications"

export const Route = createFileRoute("/_layout/settings/notifications")({
  component: NotificationsRoute,
})
