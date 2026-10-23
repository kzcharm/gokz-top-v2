export function getWrGap(recordTime: number, wrTime: number) {
  if (
    !Number.isFinite(recordTime) ||
    !Number.isFinite(wrTime) ||
    wrTime <= 0 ||
    recordTime <= wrTime
  ) {
    return null
  }

  const gap = Math.log2(recordTime / wrTime - 1)
  return Number.isFinite(gap) ? gap : null
}
