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
  const secondPart = `${secs.toString().padStart(hours > 0 ? 2 : 1, "0")}.${milliseconds
    .toString()
    .padStart(3, "0")}`

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${secondPart.padStart(6, "0")}`
  }

  return `${minutes}:${secondPart.padStart(6, "0")}`
}

export async function fetchRecentRecords(limit = RECENT_RECORDS_LIVE_LIMIT) {
  const configuredBase = OpenAPI.BASE || window.location.origin
  const baseUrl = new URL(configuredBase, window.location.origin)
  const normalizedPath =
    baseUrl.pathname === "/" ? "" : baseUrl.pathname.replace(/\/$/, "")
  const response = await fetch(
    `${baseUrl.origin}${normalizedPath}/v1/records/recent?limit=${limit}`,
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
