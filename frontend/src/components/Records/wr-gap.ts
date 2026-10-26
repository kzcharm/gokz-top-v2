import { formatFlooredDecimal } from "@/lib/number-format"

export function getWrGap(recordTime: number, wrTime: number) {
  if (
    !Number.isFinite(recordTime) ||
    !Number.isFinite(wrTime) ||
    wrTime <= 0 ||
    recordTime < wrTime
  ) {
    return null
  }
  const ratio = recordTime / wrTime
  return Number.isFinite(ratio) ? ratio : null
}

export function wrGapScaleToRatio(value: number) {
  const ratio = 1 + 2 ** value
  return Number.isFinite(value) && Number.isFinite(ratio) ? ratio : null
}

export function formatWrGap(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—"
  return `${formatFlooredDecimal(value, value > 10 ? 1 : 2)}x`
}
