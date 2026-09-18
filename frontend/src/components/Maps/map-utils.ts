import { type MapPublic, MapsService } from "@/client"
import type { AppScope } from "@/components/scope-provider"

const MAP_SKILLS = [
  { color: "#e57d2b", key: "ladder", label: "Ladder" },
  { color: "#229ac2", key: "bhop", label: "Bhop" },
  { color: "#776ba5", key: "slide", label: "Slide" },
  { color: "#26965c", key: "climb", label: "Climb" },
  { color: "#d64545", key: "strafe", label: "Strafe" },
  { color: "#b83280", key: "boxtech", label: "Boxtech" },
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

export async function fetchMapByName(mapName: string) {
  const maps = await MapsService.readMaps({
    name: mapName,
  })
  const map = maps[0]
  if (!map) {
    throw new Error("Map not found")
  }
  return map
}

export function getMapTierForScope(map: MapPublic, scope: AppScope) {
  return map.tiers[scope] ?? 0
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

function getNormalizedSkillPercentages(map: MapPublic): number[] {
  if (!map.skills) {
    return MAP_SKILLS.map((skill) => (skill.key === "unknown" ? 100 : 0))
  }
  const known = MAP_SORTABLE_SKILLS.map((skill) => map.skills?.[skill.key] ?? 0)
  const unknown = Math.max(
    0,
    1 - known.reduce((sum, fraction) => sum + fraction, 0),
  )
  return normalizeSkillPercentages(
    [...known, unknown].map((fraction) => fraction * 100),
  )
}

export function getMapSkillPercentage(
  map: MapPublic,
  skillKey: Exclude<MapSkillKey, "unknown">,
) {
  const percentages = getNormalizedSkillPercentages(map)
  const skillIndex = MAP_SKILLS.findIndex((skill) => skill.key === skillKey)

  return skillIndex >= 0 ? percentages[skillIndex] : 0
}

export function getMapSkillPortions(map: MapPublic): MapSkillPortion[] {
  const percentages = getNormalizedSkillPercentages(map)

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
