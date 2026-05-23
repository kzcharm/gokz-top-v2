import { createFileRoute } from "@tanstack/react-router"

import { MapDetailPage } from "@/components/Maps/MapDetailPage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/maps/$mapName/reviews")({
  component: MapReviewsRoute,
  head: ({ params }) => ({
    meta: [
      {
        title: getPageTitle(params.mapName),
      },
    ],
  }),
})

function MapReviewsRoute() {
  const { mapName } = Route.useParams()

  return <MapDetailPage mapName={mapName} activeTab="reviews" />
}
