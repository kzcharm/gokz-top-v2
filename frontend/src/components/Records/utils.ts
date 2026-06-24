import type { ServerGroupSummary } from "@/client"
import { OpenAPI } from "@/client"

export const RECENT_RECORDS_LIVE_LIMIT = 50

export interface RecentRecordPlayer {
  steamid64: string
  name: string
  alias: string | null
  avatar_hash: string | null
  country: string | null
}

export interface RecentRecordMap {
  id: number
  name: string
  tier: number
}

export interface RecentRecordServer {
  id: number
  name: string
  group?: ServerGroupSummary | null
}

export interface RecentRecordMode {
  id: number
  name: string
}

export interface RecentRecord {
  uuid: string
  id: number | null
  player: RecentRecordPlayer
  map: RecentRecordMap
  server: RecentRecordServer
  mode: RecentRecordMode
  stage: number
  teleports: number
  time: number
  points: number
  created_on: string
  updated_on: string
}

export interface RecentRecordsResponse {
  data: RecentRecord[]
  count: number
}

export type RecentRecordRealtimeEvent =
  | {
      type: "record.snapshot"
      records: RecentRecord[]
    }
  | {
      type: "record.upserted"
      record: RecentRecord
    }

export interface RecentRecordsFilters {
  mode?: string | null
  mapId?: number | null
  stage?: number | null
  isBonus?: boolean | null
  tier?: number | null
  type?: "NUB" | "PRO" | null
  minPoints?: number | null
  maxPoints?: number | null
}

export function buildRecentRecordsWebSocketUrl() {
  const configuredBase = OpenAPI.BASE || window.location.origin
  const baseUrl = new URL(configuredBase, window.location.origin)
  const protocol = baseUrl.protocol === "https:" ? "wss:" : "ws:"
  const normalizedPath =
    baseUrl.pathname === "/" ? "" : baseUrl.pathname.replace(/\/$/, "")

  return `${protocol}//${baseUrl.host}${normalizedPath}/v1/ws/records/recent`
}

export function compareRecentRecords(left: RecentRecord, right: RecentRecord) {
  const createdComparison =
    Date.parse(right.created_on) - Date.parse(left.created_on)
  if (createdComparison !== 0) {
    return createdComparison
  }

  const leftId = left.id ?? Number.NEGATIVE_INFINITY
  const rightId = right.id ?? Number.NEGATIVE_INFINITY
  const idComparison = rightId - leftId
  if (idComparison !== 0) {
    return idComparison
  }

  return right.uuid.localeCompare(left.uuid)
}

export function upsertRecentRecord(
  records: RecentRecord[],
  record: RecentRecord,
  limit = RECENT_RECORDS_LIVE_LIMIT,
) {
  const nextRecords = records.filter(
    (currentRecord) => currentRecord.uuid !== record.uuid,
  )
  nextRecords.push(record)
  nextRecords.sort(compareRecentRecords)
  return nextRecords.slice(0, limit)
}

export function formatStageLabel(stage: number) {
  return stage === 0 ? "Main" : `Bonus ${stage}`
}

export function formatRecordTime(seconds: number) {
  const totalMilliseconds = Math.max(0, Math.round(seconds * 1000))
  const hours = Math.floor(totalMilliseconds / 3_600_000)
  const minutes = Math.floor((totalMilliseconds % 3_600_000) / 60_000)
  const secs = Math.floor((totalMilliseconds % 60_000) / 1000)
  const milliseconds = totalMilliseconds % 1000
  const secondPart = `${secs.toString().padStart(hours > 0 || minutes > 0 ? 2 : 1, "0")}.${milliseconds
    .toString()
    .padStart(3, "0")}`

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${secondPart.padStart(6, "0")}`
  }

  if (minutes === 0) {
    return secondPart
  }

  return `${minutes}:${secondPart.padStart(6, "0")}`
}

export async function fetchRecentRecords(
  limit = RECENT_RECORDS_LIVE_LIMIT,
  filters: RecentRecordsFilters = {},
) {
  const configuredBase = OpenAPI.BASE || window.location.origin
  const baseUrl = new URL(configuredBase, window.location.origin)
  const normalizedPath =
    baseUrl.pathname === "/" ? "" : baseUrl.pathname.replace(/\/$/, "")
  const params = new URLSearchParams({ limit: String(limit) })
  if (filters.mode) {
    params.set("mode", filters.mode)
  }
  if (filters.mapId) {
    params.set("map_id", String(filters.mapId))
  }
  if (filters.stage !== null && filters.stage !== undefined) {
    params.set("stage", String(filters.stage))
  }
  if (filters.isBonus !== null && filters.isBonus !== undefined) {
    params.set("is_bonus", String(filters.isBonus))
  }
  if (filters.tier !== null && filters.tier !== undefined) {
    params.set("tier", String(filters.tier))
  }
  if (filters.type) {
    params.set("type", filters.type)
  }
  if (filters.minPoints !== null && filters.minPoints !== undefined) {
    params.set("points_more_or_equal_than", String(filters.minPoints))
  }
  if (filters.maxPoints !== null && filters.maxPoints !== undefined) {
    params.set("points_less_or_equal_than", String(filters.maxPoints))
  }
  const response = await fetch(
    `${baseUrl.origin}${normalizedPath}/v1/records/recent?${params.toString()}`,
    {
      credentials: "include",
      headers: {
        Accept: "application/json",
      },
    },
  )

  if (!response.ok) {
    throw new Error(`Failed to fetch recent records: ${response.status}`)
  }

  return (await response.json()) as RecentRecordsResponse
}
