import type { RecordPublic } from "@/client"

export type ProfileRecordDistributionBin = {
  label: string
  count: number
  topMapNames: string[]
  hasMoreMapNames: boolean
}

const MAX_POINTS = 1000
const RANGE_WIDTH = 50
const RANGE_BIN_COUNT = MAX_POINTS / RANGE_WIDTH
const MAX_TOOLTIP_MAP_RESULTS = 6

export function buildProfileRecordDistribution(
  records: RecordPublic[],
): ProfileRecordDistributionBin[] {
  const bins: ProfileRecordDistributionBin[] = Array.from(
    { length: RANGE_BIN_COUNT },
    (_, index) => {
      const start = index * RANGE_WIDTH
      const end = start + RANGE_WIDTH - 1

      return {
        label: `${start}-${end}`,
        count: 0,
        topMapNames: [],
        hasMoreMapNames: false,
      }
    },
  )

  bins.push({
    label: String(MAX_POINTS),
    count: 0,
    topMapNames: [],
    hasMoreMapNames: false,
  })
  const recordsByBin = Array.from(
    { length: bins.length },
    () => [] as RecordPublic[],
  )

  for (const record of records) {
    const points = record.points

    if (points === MAX_POINTS) {
      bins[bins.length - 1].count += 1
      recordsByBin[bins.length - 1].push(record)
      continue
    }

    if (points < 0 || points > MAX_POINTS) {
      continue
    }

    const binIndex = Math.floor(points / RANGE_WIDTH)

    if (binIndex >= 0 && binIndex < RANGE_BIN_COUNT) {
      bins[binIndex].count += 1
      recordsByBin[binIndex].push(record)
    }
  }

  recordsByBin.forEach((binRecords, index) => {
    const sortedRecords = [...binRecords].sort((left, right) => {
      if (right.points !== left.points) {
        return right.points - left.points
      }

      const mapNameComparison = left.map_name.localeCompare(
        right.map_name,
        undefined,
        {
          numeric: true,
          sensitivity: "base",
        },
      )
      if (mapNameComparison !== 0) {
        return mapNameComparison
      }

      return left.uuid.localeCompare(right.uuid)
    })

    bins[index].topMapNames = sortedRecords
      .slice(0, MAX_TOOLTIP_MAP_RESULTS)
      .map((record) => record.map_name)
    bins[index].hasMoreMapNames = sortedRecords.length > MAX_TOOLTIP_MAP_RESULTS
  })

  return bins
}
