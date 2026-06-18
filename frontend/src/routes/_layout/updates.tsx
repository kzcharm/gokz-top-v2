import { createFileRoute } from "@tanstack/react-router"

import { UpdatesPage } from "@/components/Updates/UpdatesPage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/updates")({
  component: UpdatesRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Updates"),
      },
    ],
  }),
})

function UpdatesRoute() {
  return <UpdatesPage />
}
