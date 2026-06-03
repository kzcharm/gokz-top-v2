import { createFileRoute } from "@tanstack/react-router"

import type { RecordType } from "@/client"
import { MapDetailPage } from "@/components/Maps/MapDetailPage"
import type { AppScope } from "@/components/scope-provider"
import { getPageTitle } from "@/lib/site"

const validScopes = new Set(["OVR", "KZT", "SKZ", "VNL"])
const validRecordTypes = new Set(["NUB", "PRO"])
type MapTopSearch = {
  scope?: AppScope
  type?: RecordType
}

export const Route = createFileRoute("/maps/$mapName/maptop")({
  component: MapTopRoute,
  validateSearch: (search: Record<string, unknown>): MapTopSearch => {
    const parsedSearch: MapTopSearch = {}
    if (typeof search.scope === "string" && validScopes.has(search.scope)) {
      parsedSearch.scope = search.scope as AppScope
    }
    if (typeof search.type === "string" && validRecordTypes.has(search.type)) {
      parsedSearch.type = search.type as RecordType
    }
    return parsedSearch
  },
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
  const { scope, type } = Route.useSearch()

  return (
    <MapDetailPage
      mapName={mapName}
      activeTab="top"
      initialScope={scope}
      initialRecordType={type}
    />
  )
}
