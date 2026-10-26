import { queryOptions } from "@tanstack/react-query"

import {
  type MapWrPublic,
  type RecordFirstCompletionPublic,
  type RecordPublic,
  type RecordRunHistoryPublic,
  RecordsService,
} from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { getPlayerDisplayName } from "@/components/Common/PlayerDisplay"
import { getWrGap } from "@/components/Records/wr-gap"
import type { AppScope } from "@/components/scope-provider"

export const PB_RECORDS_QUERY_LIMIT = 10_000
export const MAP_TOP_QUERY_LIMIT = 100

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
  | "stage"
  | "tps"
  | "time"
  | "rank"
  | "wrTime"
  | "wrGap"
  | "points"
  | "rating"
  | "server"
  | "datetime"
  | "firstCompletion"

export type PbRecordsSortDirection = "asc" | "desc"

export interface PbRecordsSortState {
  column: PbRecordsColumn
  direction: PbRecordsSortDirection
}

export type PbRecordWithWr = RecordPublic & {
  wr_teleports?: number | null
  first_completed_at?: string | null
}

export function attachMapWrsToPbRecords(
  records: RecordPublic[],
  wrs: MapWrPublic[],
) {
  const wrByMapId = new Map<number, MapWrPublic>()
  for (const wr of wrs) {
    if (!wrByMapId.has(wr.map_id)) {
      wrByMapId.set(wr.map_id, wr)
    }
  }

  return records.map((record) => {
    const wr = record.stage === 0 ? wrByMapId.get(record.map_id) : undefined
    return {
      ...record,
      wr_time: wr?.time ?? null,
      wr_gap: wr === undefined ? null : getWrGap(record.time, wr.time),
      wr_teleports: wr?.teleports ?? null,
    }
  })
}

function compareStrings(left: string, right: string) {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  })
}

function getRecordSortValue(column: PbRecordsColumn, record: PbRecordWithWr) {
  switch (column) {
    case "player":
      return getPlayerDisplayName(record.player)
    case "map":
      return record.map_name
    case "mode":
      return record.mode
    case "tier":
      return record.map_tier
    case "stage":
      return record.stage
    case "tps":
      return record.teleports
    case "time":
      return record.time
    case "rank":
      return record.rank ?? Number.POSITIVE_INFINITY
    case "wrTime":
      return record.wr_time ?? Number.POSITIVE_INFINITY
    case "wrGap":
      return record.wr_gap ?? Number.POSITIVE_INFINITY
    case "points":
      return record.points
    case "rating":
      return record.raw_rating_contribution ?? 0
    case "server":
      return record.server_name
    case "datetime":
      return Date.parse(record.created_on)
    case "firstCompletion":
      return Date.parse(record.first_completed_at ?? "")
  }
}

export function sortPbRecords<Record extends PbRecordWithWr>(
  records: Record[],
  sort: PbRecordsSortState,
) {
  return [...records].sort((left, right) => {
    if (sort.column === "firstCompletion") {
      const leftMissing = !Number.isFinite(
        Date.parse(left.first_completed_at ?? ""),
      )
      const rightMissing = !Number.isFinite(
        Date.parse(right.first_completed_at ?? ""),
      )
      if (leftMissing || rightMissing) {
        if (leftMissing !== rightMissing) return leftMissing ? 1 : -1
        return compareStrings(left.uuid, right.uuid)
      }
    }
    if (sort.column === "rank" && (left.rank == null || right.rank == null)) {
      if (left.rank == null && right.rank != null) return 1
      if (left.rank != null && right.rank == null) return -1
      return compareStrings(left.uuid, right.uuid)
    }
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
  identifier,
  scope,
  isProOnly,
  isBonus,
  stage,
}: {
  identifier: string | null
  scope: AppScope
  isProOnly: boolean
  isBonus: boolean
  stage: number | null
}) {
  return queryOptions({
    queryKey: [
      "profile-records",
      identifier,
      scope,
      isProOnly,
      isBonus,
      stage ?? 0,
    ],
    queryFn: async () => {
      if (!identifier) {
        return []
      }

      const params = new URLSearchParams({
        identifier,
        scope,
        stage: String(stage ?? 0),
        is_bonus: String(isBonus),
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

export function getProfileFirstCompletionsQueryOptions({
  identifier,
  scope,
  isProOnly,
  isBonus,
  stage,
  enabled,
}: {
  identifier: string
  scope: AppScope
  isProOnly: boolean
  isBonus: boolean
  stage: number | null
  enabled: boolean
}) {
  return queryOptions({
    // Share the PB invalidation prefix without replacing its cached response.
    queryKey: [
      "profile-records",
      identifier,
      "first-completions",
      scope,
      isProOnly,
      isBonus,
      stage ?? 0,
    ],
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams({
        identifier,
        scope,
        type: isProOnly ? "PRO" : "NUB",
        is_bonus: String(isBonus),
        stage: String(stage ?? 0),
      })
      const response = await fetch(
        `${OpenAPI.BASE}/v1/records/pb/first-completions?${params}`,
        {
          credentials: OpenAPI.CREDENTIALS,
          signal,
        },
      )
      if (!response.ok) throw new Error("Failed to load first completion times")
      return (await response.json()) as RecordFirstCompletionPublic[]
    },
    ...PB_RECORDS_QUERY_CONFIG,
    enabled,
    retry: false,
  })
}

export function getMapPbRecordsQueryOptions({
  mapId,
  scope,
  isProOnly,
  country,
  region,
}: {
  mapId: number | null
  scope: AppScope
  isProOnly: boolean
  country: string | null
  region: string | null
}) {
  return queryOptions({
    queryKey: ["map-records", mapId, scope, isProOnly, country, region],
    queryFn: async () => {
      if (mapId === null) {
        return []
      }

      return await RecordsService.readPbRecords({
        mapId,
        scope,
        stage: 0,
        type: isProOnly ? "PRO" : "NUB",
        country: country ?? undefined,
        region: region ?? undefined,
        limit: MAP_TOP_QUERY_LIMIT,
      })
    },
    ...PB_RECORDS_QUERY_CONFIG,
  })
}

export function getRecordRunHistoryQueryOptions({
  identifier,
  mapId,
  stage,
  scope,
  type,
  enabled = true,
}: {
  identifier: string | null
  mapId: number | null
  stage: number
  scope: AppScope
  type: "NUB" | "PRO"
  enabled?: boolean
}) {
  return queryOptions({
    queryKey: ["record-run-history", identifier, mapId, stage, scope, type],
    queryFn: async () => {
      if (!identifier || mapId === null) {
        return {
          data: [],
          count: 0,
          wr_time: null,
        } satisfies RecordRunHistoryPublic
      }

      const params = new URLSearchParams({
        identifier,
        map_id: String(mapId),
        stage: String(stage),
        scope,
        type,
      })
      const response = await fetch(
        `${OpenAPI.BASE}/v1/records/run-history?${params.toString()}`,
        {
          credentials: OpenAPI.CREDENTIALS,
        },
      )
      if (!response.ok) {
        throw new Error("Failed to load run history")
      }

      return (await response.json()) as RecordRunHistoryPublic
    },
    enabled: enabled && Boolean(identifier) && mapId !== null,
    staleTime: 30_000,
    retry: 1,
  })
}

export function getPbPageRanksQueryOptions(
  uuids: string[],
  scope: AppScope,
  isProOnly: boolean,
  enabled: boolean,
) {
  const ids = [...uuids].sort()
  return queryOptions({
    queryKey: ["pb-page-ranks", scope, isProOnly, ids],
    queryFn: async ({ signal }) => {
      if (ids.length > 50)
        throw new Error("Rank requests support at most 50 records")
      const params = new URLSearchParams({
        scope,
        type: isProOnly ? "PRO" : "NUB",
      })
      for (const id of ids) params.append("uuid_list", id)
      const response = await fetch(
        `${OpenAPI.BASE}/v1/records/pb/ranks?${params}`,
        {
          credentials: OpenAPI.CREDENTIALS,
          signal,
        },
      )
      if (!response.ok) throw new Error("Failed to load record ranks")
      return (await response.json()) as Record<string, number | null>
    },
    enabled: enabled && ids.length > 0,
    staleTime: 30_000,
    retry: 1,
  })
}
