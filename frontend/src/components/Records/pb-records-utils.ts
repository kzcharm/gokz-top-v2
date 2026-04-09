import { queryOptions } from "@tanstack/react-query"

import type { RecordPublic, RecordType } from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { getPlayerDisplayName } from "@/components/Common/PlayerDisplay"
import type { AppScope } from "@/components/scope-provider"

export const PB_RECORDS_QUERY_LIMIT = 10_000

const PB_RECORDS_QUERY_CONFIG = {
  staleTime: Number.POSITIVE_INFINITY,
  gcTime: Number.POSITIVE_INFINITY,
  refetchOnMount: false,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  retry: 1,
} as const

export type PbRecordsColumn =
  | "player"
  | "map"
  | "mode"
  | "tier"
  | "tps"
  | "time"
  | "points"
  | "server"
  | "datetime"

export type PbRecordsSortDirection = "asc" | "desc"

export interface PbRecordsSortState {
  column: PbRecordsColumn
  direction: PbRecordsSortDirection
}

function compareStrings(left: string, right: string) {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  })
}

function getRecordSortValue(column: PbRecordsColumn, record: RecordPublic) {
  switch (column) {
    case "player":
      return getPlayerDisplayName(record.player)
    case "map":
      return record.map_name
    case "mode":
      return record.mode
    case "tier":
      return record.map_tier
    case "tps":
      return record.teleports
    case "time":
      return record.time
    case "points":
      return record.points
    case "server":
      return record.server_name
    case "datetime":
      return Date.parse(record.created_on)
  }
}

export function sortPbRecords(
  records: RecordPublic[],
  sort: PbRecordsSortState,
) {
  return [...records].sort((left, right) => {
    const leftValue = getRecordSortValue(sort.column, left)
    const rightValue = getRecordSortValue(sort.column, right)

    let comparison = 0
    if (typeof leftValue === "string" && typeof rightValue === "string") {
      comparison = compareStrings(leftValue, rightValue)
    } else {
      comparison = Number(leftValue) - Number(rightValue)
    }

    if (comparison === 0) {
      comparison = compareStrings(left.uuid, right.uuid)
    }

    return sort.direction === "asc" ? comparison : -comparison
  })
}

export function getProfilePbRecordsQueryOptions({
  steamid64,
  scope,
  isProOnly,
}: {
  steamid64: string | null
  scope: AppScope
  isProOnly: boolean
}) {
  return queryOptions({
    queryKey: ["profile-records", steamid64, scope, isProOnly],
    queryFn: async () => {
      if (!steamid64) {
        return []
      }

      const params = new URLSearchParams({
        steamid64,
        scope,
        stage: "0",
        type: isProOnly ? "PRO" : "NUB",
        exclude_cheaters: "false",
        limit: String(PB_RECORDS_QUERY_LIMIT),
      })
      const response = await fetch(
        `${OpenAPI.BASE}/v1/records/pb?${params.toString()}`,
        {
          credentials: OpenAPI.CREDENTIALS,
        },
      )
      if (!response.ok) {
        throw new Error("Failed to load profile PB records")
      }

      return (await response.json()) as RecordPublic[]
    },
    ...PB_RECORDS_QUERY_CONFIG,
  })
}

export function getMapPbRecordsQueryOptions({
  mapId,
  mapName,
  scope,
  isProOnly,
}: {
  mapId: number | null
  mapName: string | null
  scope: AppScope
  isProOnly: boolean
}) {
  return queryOptions({
    queryKey: ["map-records", mapId, mapName, scope, isProOnly],
    queryFn: async (): Promise<RecordPublic[]> => {
      if (mapId === null && !mapName) {
        return []
      }

      const recordType: RecordType = isProOnly ? "PRO" : "NUB"
      const params = new URLSearchParams({
        scope,
        stage: "0",
        type: recordType,
        exclude_cheaters: "false",
        limit: String(PB_RECORDS_QUERY_LIMIT),
      })

      if (mapId !== null) {
        params.set("map_id", String(mapId))
      } else if (mapName) {
        params.set("map_name", mapName)
      }

      const response = await fetch(
        `${OpenAPI.BASE}/v1/records/pb?${params.toString()}`,
        {
          credentials: OpenAPI.CREDENTIALS,
        },
      )
      if (!response.ok) {
        throw new Error("Failed to load map PB records")
      }

      return (await response.json()) as RecordPublic[]
    },
    ...PB_RECORDS_QUERY_CONFIG,
  })
}
