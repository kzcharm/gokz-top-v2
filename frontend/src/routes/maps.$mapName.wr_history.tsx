import { createFileRoute } from "@tanstack/react-router"

import type { RecordType } from "@/client"
import { MapDetailPage } from "@/components/Maps/MapDetailPage"
import type { AppScope } from "@/components/scope-provider"
import { getPageTitle } from "@/lib/site"

const validScopes = new Set(["OVR", "KZT", "SKZ", "VNL"])
const validRecordTypes = new Set(["NUB", "PRO"])

type MapWrHistorySearch = {
  scope?: AppScope
  type?: RecordType
}

export const Route = createFileRoute("/maps/$mapName/wr_history")({
  component: MapWrHistoryRoute,
  validateSearch: (search: Record<string, unknown>): MapWrHistorySearch => {
    const parsedSearch: MapWrHistorySearch = {}
    if (typeof search.scope === "string" && validScopes.has(search.scope)) {
      parsedSearch.scope = search.scope as AppScope
    }
    if (typeof search.type === "string" && validRecordTypes.has(search.type)) {
      parsedSearch.type = search.type as RecordType
    }
    return parsedSearch
  },
  head: ({ params }) => ({
    meta: [{ title: getPageTitle(params.mapName) }],
  }),
})

function MapWrHistoryRoute() {
  const { mapName } = Route.useParams()
  const { scope, type } = Route.useSearch()

  return (
    <MapDetailPage
      mapName={mapName}
      activeTab="wrHistory"
      initialScope={scope}
      initialRecordType={type}
    />
  )
}
