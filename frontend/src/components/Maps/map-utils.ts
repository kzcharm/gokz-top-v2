import { MapsService } from "@/client"
import mapSkillAnalysisData from "@/data/map-skill-analysis.json"

const MAP_SKILLS = [
  { color: "#d29922", key: "ladder", label: "Ladder" },
  { color: "#3fb950", key: "bhop", label: "Bhop" },
  { color: "#8b72d9", key: "slide", label: "Slide" },
  { color: "#7fb77e", key: "climb", label: "Climb" },
  { color: "#58a6ff", key: "strafe", label: "Strafe" },
  { color: "#e5534b", key: "route", label: "Route" },
  { color: "#8b949e", key: "unknown", label: "Unknown" },
] as const

export type MapSkillKey = (typeof MAP_SKILLS)[number]["key"]
export const MAP_SORTABLE_SKILLS = MAP_SKILLS.filter(
  (skill) => skill.key !== "unknown",
)

export interface MapSkillPortion {
  color: (typeof MAP_SKILLS)[number]["color"]
  label: (typeof MAP_SKILLS)[number]["label"]
  percentage: number
}

interface SkillRemainderEntry {
  index: number
  remainder: number
}

interface MapSkillSummary {
  skill: MapSkillKey
  percentage: number
}

interface MapSkillAnalysisMap {
  map_name: string
  summaries: MapSkillSummary[]
}

interface MapSkillAnalysisData {
  maps: MapSkillAnalysisMap[]
}

const mapSkillPortionsByName = new Map<string, Record<MapSkillKey, number>>(
  (mapSkillAnalysisData as MapSkillAnalysisData).maps.map((entry) => [
    entry.map_name.toLowerCase(),
    entry.summaries.reduce<Record<MapSkillKey, number>>(
      (skillPortions, summary) => {
        skillPortions[summary.skill] = summary.percentage * 100
        return skillPortions
      },
      {
        ladder: 0,
        bhop: 0,
        slide: 0,
        climb: 0,
        strafe: 0,
        route: 0,
        unknown: 0,
      },
    ),
  ]),
)

export async function fetchMapByName(mapName: string) {
  return await MapsService.readMapByName({
    mapName,
  })
}

function hashString(value: string) {
  let hash = 2166136261

  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }

  return hash >>> 0
}

function createSeededRandom(seed: number) {
  let state = seed || 1

  return function nextRandom() {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0
    return state / 4294967296
  }
}

function normalizeSkillPercentages(
  rawPercentages: readonly number[],
): number[] {
  const total = rawPercentages.reduce((sum, percentage) => sum + percentage, 0)

  if (total <= 0) {
    return new Array(rawPercentages.length).fill(0)
  }

  const exactShares = rawPercentages.map(
    (percentage) => (percentage / total) * 100,
  )
  const flooredShares = exactShares.map(Math.floor)
  const allocatedShare = flooredShares.reduce((sum, value) => sum + value, 0)
  const remainingShare = 100 - allocatedShare
  const normalizedPercentages = [...flooredShares]

  const remainderOrder: SkillRemainderEntry[] = [...exactShares]
    .map((share, index) => ({
      index,
      remainder: share - flooredShares[index],
    }))
    .sort(
      (left, right) =>
        right.remainder - left.remainder || left.index - right.index,
    )

  for (let index = 0; index < remainingShare; index += 1) {
    normalizedPercentages[remainderOrder[index].index] += 1
  }

  return normalizedPercentages
}

function buildSeededSkillPercentages(mapName: string) {
  const nextRandom = createSeededRandom(hashString(mapName))
  const dominantSkillIndex = Math.floor(nextRandom() * MAP_SKILLS.length)
  const weights = MAP_SKILLS.map((_, index) => {
    const baseWeight = nextRandom() * 100 + 10
    return index === dominantSkillIndex ? baseWeight + 140 : baseWeight
  })

  const guaranteedWeights = weights.map((weight) => weight + 1)
  return normalizeSkillPercentages(guaranteedWeights)
}

function getNormalizedSkillPercentages(mapName: string): number[] {
  const skillPortionsRecord = mapSkillPortionsByName.get(mapName.toLowerCase())
  return skillPortionsRecord
    ? normalizeSkillPercentages(
        MAP_SKILLS.map((skill) => skillPortionsRecord[skill.key] ?? 0),
      )
    : buildSeededSkillPercentages(mapName)
}

export function getMapSkillPercentage(
  mapName: string,
  skillKey: Exclude<MapSkillKey, "unknown">,
) {
  const percentages = getNormalizedSkillPercentages(mapName)
  const skillIndex = MAP_SKILLS.findIndex((skill) => skill.key === skillKey)

  return skillIndex >= 0 ? percentages[skillIndex] : 0
}

export function getMapSkillPortions(mapName: string): MapSkillPortion[] {
  const percentages = getNormalizedSkillPercentages(mapName)

  return [...MAP_SKILLS]
    .map((skill, index) => ({
      ...skill,
      percentage: percentages[index],
    }))
    .sort(
      (left, right) =>
        right.percentage - left.percentage ||
        left.label.localeCompare(right.label),
    )
}
