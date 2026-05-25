export type BanStatus = "permanent" | "active" | "expired" | "unbanned"

export const BAN_LENGTH_OPTIONS = [
  { value: "permanent", label: "Permanent" },
  { value: "1_week", label: "1 Week" },
  { value: "1_month", label: "1 Month" },
  { value: "3_months", label: "3 Months" },
  { value: "1_year", label: "1 Year" },
  { value: "3_years", label: "3 Years" },
] as const

export type BanLengthValue = (typeof BAN_LENGTH_OPTIONS)[number]["value"]

export function formatBanTypeLabel(banType: string) {
  return banType
    .split("_")
    .map((segment) =>
      segment.length > 0
        ? `${segment[0].toUpperCase()}${segment.slice(1)}`
        : "",
    )
    .join(" ")
}

export function isBanManuallyUnbanned({
  createdAt,
  expiresAt,
}: {
  createdAt: string
  expiresAt: string | null
}) {
  if (!expiresAt) {
    return false
  }

  const createdAtMs = new Date(createdAt).getTime()
  const expiresAtMs = new Date(expiresAt).getTime()
  if (Number.isNaN(createdAtMs) || Number.isNaN(expiresAtMs)) {
    return false
  }

  return expiresAtMs <= createdAtMs
}

export function getBanStatus({
  createdAt,
  expiresAt,
  now = Date.now(),
}: {
  createdAt: string
  expiresAt: string | null
  now?: number
}): BanStatus {
  if (!expiresAt) {
    return "permanent"
  }

  if (isBanManuallyUnbanned({ createdAt, expiresAt })) {
    return "unbanned"
  }

  const expiresAtMs = new Date(expiresAt).getTime()
  if (Number.isNaN(expiresAtMs)) {
    return "active"
  }

  if (expiresAtMs < now) {
    return "expired"
  }

  return "active"
}

export function getUnbanExpiresAtIso(createdAt: string) {
  const createdAtDate = new Date(createdAt)
  createdAtDate.setUTCDate(createdAtDate.getUTCDate() - 1)
  return createdAtDate.toISOString()
}

export function getBanExpiryIsoFromDate(
  baseValue: Date | string,
  length: BanLengthValue,
) {
  if (length === "permanent") {
    return null
  }

  const expiresAt =
    typeof baseValue === "string" ? new Date(baseValue) : new Date(baseValue)
  if (Number.isNaN(expiresAt.getTime())) {
    return null
  }

  switch (length) {
    case "1_week":
      expiresAt.setUTCDate(expiresAt.getUTCDate() + 7)
      break
    case "1_month":
      expiresAt.setUTCMonth(expiresAt.getUTCMonth() + 1)
      break
    case "3_months":
      expiresAt.setUTCMonth(expiresAt.getUTCMonth() + 3)
      break
    case "1_year":
      expiresAt.setUTCFullYear(expiresAt.getUTCFullYear() + 1)
      break
    case "3_years":
      expiresAt.setUTCFullYear(expiresAt.getUTCFullYear() + 3)
      break
  }

  return expiresAt.toISOString()
}

export function getBanLengthValueForExpiry({
  createdAt,
  expiresAt,
}: {
  createdAt: string
  expiresAt: string | null
}): BanLengthValue | "custom" {
  if (!expiresAt) {
    return "permanent"
  }

  for (const option of BAN_LENGTH_OPTIONS) {
    if (option.value === "permanent") {
      continue
    }

    if (getBanExpiryIsoFromDate(createdAt, option.value) === expiresAt) {
      return option.value
    }
  }

  return "custom"
}

export function isoToLocalDateTimeInputValue(value: string | null) {
  if (!value) {
    return ""
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ""
  }

  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, "0")
  const day = `${date.getDate()}`.padStart(2, "0")
  const hours = `${date.getHours()}`.padStart(2, "0")
  const minutes = `${date.getMinutes()}`.padStart(2, "0")
  return `${year}-${month}-${day}T${hours}:${minutes}`
}

export function localDateTimeInputValueToIso(value: string) {
  if (!value.trim()) {
    return null
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return null
  }

  return date.toISOString()
}
