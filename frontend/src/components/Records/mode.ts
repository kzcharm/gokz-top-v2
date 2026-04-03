export const RECORD_MODE_OPTIONS = [
  {
    label: "KZT",
    style: { backgroundColor: "#4a95d9" },
    textClassName: "border-transparent text-white",
    value: "KZT",
  },
  {
    label: "SKZ",
    style: { backgroundColor: "#4ebd78" },
    textClassName: "border-transparent text-white",
    value: "SKZ",
  },
  {
    label: "VNL",
    style: { backgroundColor: "#f69231" },
    textClassName: "border-transparent text-white",
    value: "VNL",
  },
  {
    label: "NKZ",
    style: { backgroundColor: "#2f6fb0" },
    textClassName: "border-transparent text-white",
    value: "NKZ",
  },
] as const

export type RecordMode = (typeof RECORD_MODE_OPTIONS)[number]["value"]

export function normalizeRecordMode(mode: string) {
  return mode.trim().toUpperCase()
}

export function getRecordModeOption(mode: string) {
  const normalizedMode = normalizeRecordMode(mode)

  return RECORD_MODE_OPTIONS.find((option) => option.value === normalizedMode)
}
