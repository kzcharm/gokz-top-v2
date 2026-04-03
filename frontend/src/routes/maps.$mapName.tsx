import { createFileRoute } from "@tanstack/react-router"

import { MapDetailPage } from "@/components/Maps/MapDetailPage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/maps/$mapName")({
  component: MapRoute,
  head: ({ params }) => ({
    meta: [
      {
        title: getPageTitle(params.mapName),
      },
    ],
  }),
})

function MapRoute() {
  const { mapName } = Route.useParams()

  return <MapDetailPage mapName={mapName} />
}
