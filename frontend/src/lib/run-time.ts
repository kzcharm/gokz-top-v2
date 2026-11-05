export const RUN_TIME_FONT_FAMILIES = {
  inter: '"Inter", sans-serif',
  "roboto-mono": '"Roboto Mono", monospace',
  "plus-jakarta-sans": '"Plus Jakarta Sans", sans-serif',
} as const
export type RunTimeFont = keyof typeof RUN_TIME_FONT_FAMILIES
export const RUN_TIME_FONT_NAMES: Record<RunTimeFont, string> = {
  inter: "Inter",
  "roboto-mono": "Roboto Mono",
  "plus-jakarta-sans": "Plus Jakarta Sans",
}

export function formatRunTime(seconds: number, showMilliseconds = true) {
  if (!Number.isFinite(seconds)) return "—"
  const totalMilliseconds = Math.max(0, Math.round(seconds * 1000))
  const hours = Math.floor(totalMilliseconds / 3_600_000)
  const minutes = Math.floor((totalMilliseconds % 3_600_000) / 60_000)
  const secs = Math.floor((totalMilliseconds % 60_000) / 1000)
  const milliseconds = totalMilliseconds % 1000
  const secondPart = `${secs.toString().padStart(2, "0")}${
    showMilliseconds ? `.${milliseconds.toString().padStart(3, "0")}` : ""
  }`
  return hours > 0
    ? `${hours}:${minutes.toString().padStart(2, "0")}:${secondPart}`
    : `${minutes}:${secondPart}`
}
