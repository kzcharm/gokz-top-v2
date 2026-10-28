import type { MapLeaderboardEntryPublic, RecordPublic } from "@/client"
import { getWrGap } from "@/components/Records/wr-gap"

export const MAP_METRICS = [
  "nub",
  "pro",
  "playtime",
  "avgPlaytime",
  "proRatio",
  "finishes",
  "firstMed",
  "firstMedWrGap",
  "bonus",
] as const
export type MapMetric = (typeof MAP_METRICS)[number]

export function isMapMetric(value: string): value is MapMetric {
  return MAP_METRICS.some((metric) => metric === value)
}

export function getFirstMedianWrGap(
  entry: MapLeaderboardEntryPublic | null | undefined,
  wrTime: number | null | undefined,
) {
  return entry && wrTime != null
    ? getWrGap(entry.median_first_completion_time, wrTime)
    : null
}

export const PERSONAL_SORTS = [
  "pbTime",
  "pbTeleports",
  "pbPoints",
  "pbRating",
  "pbDate",
  "pbWrGap",
] as const
export type PersonalSort = (typeof PERSONAL_SORTS)[number]

export function isPersonalSort(value: string): value is PersonalSort {
  return PERSONAL_SORTS.some((field) => field === value)
}

export function getPersonalSortValue(
  record: RecordPublic | undefined,
  field: PersonalSort,
  wrTime: number | undefined,
): number | null {
  if (!record) return null
  switch (field) {
    case "pbTime":
      return record.time
    case "pbTeleports":
      return record.teleports
    case "pbPoints":
      return record.points
    case "pbRating":
      return record.raw_rating_contribution ?? 0
    case "pbDate":
      return Date.parse(record.created_on)
    case "pbWrGap":
      return wrTime === undefined ? null : getWrGap(record.time, wrTime)
  }
}

export const DEFAULT_MAP_CARD_OPTIONS = {
  milliseconds: true,
  points: true,
  reviews: true,
  wr: true,
  dates: true,
  authors: true,
  skills: true,
}
export type MapCardOptions = typeof DEFAULT_MAP_CARD_OPTIONS
export const MAP_CARD_OPTIONS_STORAGE_KEY = "gokz.maps.card-options.v1"

export function readMapCardOptions(): MapCardOptions {
  try {
    const parsed: unknown = JSON.parse(
      localStorage.getItem(MAP_CARD_OPTIONS_STORAGE_KEY) ?? "null",
    )
    const options = { ...DEFAULT_MAP_CARD_OPTIONS }
    if (parsed && typeof parsed === "object") {
      for (const key of Object.keys(options) as (keyof MapCardOptions)[]) {
        const value = (parsed as Record<string, unknown>)[key]
        if (typeof value === "boolean") options[key] = value
      }
    }
    return options
  } catch {
    return { ...DEFAULT_MAP_CARD_OPTIONS }
  }
}
