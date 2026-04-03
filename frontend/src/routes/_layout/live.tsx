import { createFileRoute } from "@tanstack/react-router"

import { FeaturePlaceholder } from "@/components/Common/FeaturePlaceholder"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/live")({
  component: LiveRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Live"),
      },
    ],
  }),
})

function LiveRoute() {
  return (
    <FeaturePlaceholder
      section="Live"
      title="Live"
      description="The live page is not implemented yet. This placeholder route is here so the sidebar can expose the planned live stream and activity area."
      backTo="/maps"
      backLabel="Go to maps"
    />
  )
}
