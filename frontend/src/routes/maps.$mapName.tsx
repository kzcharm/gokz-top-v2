import { createFileRoute, Link } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/maps/$mapName")({
  component: MapPlaceholderRoute,
  head: ({ params }) => ({
    meta: [
      {
        title: getPageTitle(params.mapName),
      },
    ],
  }),
})

function MapPlaceholderRoute() {
  const { mapName } = Route.useParams()

  return (
    <div className="mx-auto max-w-5xl space-y-6 rounded-2xl border border-border/70 bg-card/60 p-6 shadow-sm backdrop-blur-sm sm:p-8">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-[0.16em] text-muted-foreground">
          Maps
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">{mapName}</h1>
        <p className="max-w-2xl text-sm text-muted-foreground sm:text-base">
          Map page coming soon. This placeholder route is in place so catalog
          navigation works while the full map detail experience is built.
        </p>
      </div>

      <Button asChild variant="outline">
        <Link to="/maps">Back to maps</Link>
      </Button>
    </div>
  )
}
