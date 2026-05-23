import { createFileRoute } from "@tanstack/react-router"

import { MapDetailPage } from "@/components/Maps/MapDetailPage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/maps/$mapName/maptop")({
  component: MapTopRoute,
  head: ({ params }) => ({
    meta: [
      {
        title: getPageTitle(params.mapName),
      },
    ],
  }),
})

function MapTopRoute() {
  const { mapName } = Route.useParams()

  return <MapDetailPage mapName={mapName} activeTab="top" />
}
