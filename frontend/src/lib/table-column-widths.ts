export type TableColumnWidth = {
  width: number
  maxWidth?: number
  grow?: boolean
}

/** Grow capped text first, then share remaining space across metrics and dates. */
export function distributeTableColumnWidths(
  columns: TableColumnWidth[],
  availableWidth: number,
): number[] {
  const minimumWidth = columns.reduce(
    (total, column) => total + column.width,
    0,
  )
  const surplus = Math.max(0, availableWidth - minimumWidth)
  const cappedGrowth = columns.reduce(
    (total, column) =>
      total + Math.max(0, (column.maxWidth ?? column.width) - column.width),
    0,
  )
  const textGrowth = Math.min(surplus, cappedGrowth)
  const growCount = columns.filter((column) => column.grow).length
  const sharedGrowth = growCount > 0 ? (surplus - textGrowth) / growCount : 0

  return columns.map((column) => {
    const capacity = Math.max(
      0,
      (column.maxWidth ?? column.width) - column.width,
    )
    return (
      column.width +
      (cappedGrowth > 0 ? (textGrowth * capacity) / cappedGrowth : 0) +
      (column.grow ? sharedGrowth : 0)
    )
  })
}
