export type DateTimePreset = "iso" | "us" | "euro" | "long"

export type DateTimeDisplay = "absolute" | "relative"

export type HourCyclePreference = "24h" | "12h"

export type DateTimeFormatOptions = {
  includeSeconds?: boolean
  display?: DateTimeDisplay
  fallback?: string
  locale?: string
  hourCycle?: HourCyclePreference
}

export const DATE_TIME_FORMAT_STORAGE_KEY = "gokz-datetime-format"
export const HOUR_CYCLE_STORAGE_KEY = "gokz-hour-cycle"

const PREVIEW_SAMPLE = new Date(2026, 2, 22, 14, 5, 9)

export function getBrowserLocale() {
  if (typeof navigator === "undefined" || !navigator.language) {
    return "en-US"
  }

  return navigator.language
}

export function isDateTimePreset(value: string | null): value is DateTimePreset {
  return value === "iso" || value === "us" || value === "euro" || value === "long"
}

export function isHourCyclePreference(
  value: string | null,
): value is HourCyclePreference {
  return value === "24h" || value === "12h"
}

export const DATE_TIME_PRESET_OPTIONS: Array<{
  value: DateTimePreset
  label: string
  description: string
}> = [
  {
    value: "iso",
    label: "ISO-like",
    description: "Year-first layout for the clearest sortable timestamp shape.",
  },
  {
    value: "us",
    label: "US",
    description: "Compact month/day layout.",
  },
  {
    value: "euro",
    label: "Euro",
    description: "Compact day-first layout.",
  },
  {
    value: "long",
    label: "Long",
    description: "Readable month-name layout.",
  },
]

export const HOUR_CYCLE_OPTIONS: Array<{
  value: HourCyclePreference
  label: string
  description: string
}> = [
  {
    value: "24h",
    label: "24-hour",
    description: "Shows times like 14:05.",
  },
  {
    value: "12h",
    label: "12-hour",
    description: "Shows times like 2:05 PM.",
  },
]

const SECOND_IN_MS = 1000
const MINUTE_IN_MS = 60 * SECOND_IN_MS
const HOUR_IN_MS = 60 * MINUTE_IN_MS
const DAY_IN_MS = 24 * HOUR_IN_MS
const WEEK_IN_MS = 7 * DAY_IN_MS
const MONTH_IN_MS = 30 * DAY_IN_MS
const YEAR_IN_MS = 365 * DAY_IN_MS

type SupportedRelativeUnit =
  | "year"
  | "month"
  | "week"
  | "day"
  | "hour"
  | "minute"
  | "second"

const RELATIVE_UNITS: Array<{
  unit: SupportedRelativeUnit
  sizeInMs: number
}> = [
  { unit: "year", sizeInMs: YEAR_IN_MS },
  { unit: "month", sizeInMs: MONTH_IN_MS },
  { unit: "week", sizeInMs: WEEK_IN_MS },
  { unit: "day", sizeInMs: DAY_IN_MS },
  { unit: "hour", sizeInMs: HOUR_IN_MS },
  { unit: "minute", sizeInMs: MINUTE_IN_MS },
  { unit: "second", sizeInMs: SECOND_IN_MS },
]

function padNumber(value: number) {
  return value.toString().padStart(2, "0")
}

function toDate(value: string | Date | null | undefined) {
  if (!value) {
    return null
  }

  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) {
    return null
  }

  return date
}

function getIsoLikeTime(date: Date, includeSeconds: boolean, hourCycle: HourCyclePreference) {
  const minutes = padNumber(date.getMinutes())
  const seconds = padNumber(date.getSeconds())

  if (hourCycle === "12h") {
    const hours24 = date.getHours()
    const meridiem = hours24 >= 12 ? "PM" : "AM"
    const hours12 = hours24 % 12 || 12
    const formattedTime = includeSeconds
      ? `${padNumber(hours12)}:${minutes}:${seconds} ${meridiem}`
      : `${padNumber(hours12)}:${minutes} ${meridiem}`
    return formattedTime
  }

  const hours24 = padNumber(date.getHours())
  return includeSeconds
    ? `${hours24}:${minutes}:${seconds}`
    : `${hours24}:${minutes}`
}

function formatIsoLike(
  date: Date,
  includeSeconds: boolean,
  hourCycle: HourCyclePreference,
) {
  const year = date.getFullYear()
  const month = padNumber(date.getMonth() + 1)
  const day = padNumber(date.getDate())
  const time = getIsoLikeTime(date, includeSeconds, hourCycle)

  return `${year}-${month}-${day} ${time}`
}

function getIntlHourOptions(
  includeSeconds: boolean,
  hourCycle: HourCyclePreference,
) {
  return {
    hour: hourCycle === "24h" ? "2-digit" : "numeric",
    minute: "2-digit",
    second: includeSeconds ? "2-digit" : undefined,
    hour12: hourCycle === "12h",
  } as const
}

function formatAbsoluteDateTime({
  date,
  preset,
  locale,
  includeSeconds,
  hourCycle,
}: {
  date: Date
  preset: DateTimePreset
  locale: string
  includeSeconds: boolean
  hourCycle: HourCyclePreference
}) {
  switch (preset) {
    case "iso":
      return formatIsoLike(date, includeSeconds, hourCycle)
    case "us":
      return new Intl.DateTimeFormat("en-US", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        ...getIntlHourOptions(includeSeconds, hourCycle),
      }).format(date)
    case "euro":
      return new Intl.DateTimeFormat("en-GB", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        ...getIntlHourOptions(includeSeconds, hourCycle),
      }).format(date)
    case "long":
    default:
      return new Intl.DateTimeFormat(locale, {
        year: "numeric",
        month: "long",
        day: "numeric",
        ...getIntlHourOptions(includeSeconds, hourCycle),
      }).format(date)
  }
}

function getRelativeUnit(diffInMs: number) {
  const absoluteDiff = Math.abs(diffInMs)

  for (const relativeUnit of RELATIVE_UNITS) {
    if (
      absoluteDiff >= relativeUnit.sizeInMs ||
      relativeUnit.unit === "second"
    ) {
      const value = Math.max(1, Math.floor(absoluteDiff / relativeUnit.sizeInMs))
      return {
        unit: relativeUnit.unit,
        value,
      }
    }
  }

  return {
    unit: "second" as const,
    value: 1,
  }
}

function formatEnglishRelativeTime(
  value: number,
  unit: SupportedRelativeUnit,
  isPast: boolean,
) {
  const labels: Record<SupportedRelativeUnit, { one: string; other: string }> = {
    year: { one: "year", other: "years" },
    month: { one: "month", other: "months" },
    week: { one: "week", other: "weeks" },
    day: { one: "day", other: "days" },
    hour: { one: "hour", other: "hours" },
    minute: { one: "min", other: "min" },
    second: { one: "second", other: "seconds" },
  }

  const label = value === 1 ? labels[unit].one : labels[unit].other
  return isPast ? `${value} ${label} ago` : `in ${value} ${label}`
}

function formatRelativeDateTime(date: Date, locale: string) {
  const diffInMs = date.getTime() - Date.now()
  const isPast = diffInMs < 0
  const { unit, value } = getRelativeUnit(diffInMs)

  if (locale.toLowerCase().startsWith("en")) {
    return formatEnglishRelativeTime(value, unit, isPast)
  }

  const formatter = new Intl.RelativeTimeFormat(locale, {
    numeric: "always",
    style: "short",
  })

  return formatter.format(isPast ? -value : value, unit)
}

export function formatDateTimeWithPreset(
  value: string | Date | null | undefined,
  {
    preset,
    hourCycle = "24h",
    includeSeconds = false,
    display = "absolute",
    fallback = "Unknown",
    locale,
  }: DateTimeFormatOptions & {
    preset: DateTimePreset
    hourCycle?: HourCyclePreference
  },
) {
  const date = toDate(value)
  if (!date) {
    return fallback
  }

  const resolvedLocale = locale ?? getBrowserLocale()

  if (display === "relative") {
    return formatRelativeDateTime(date, resolvedLocale)
  }

  return formatAbsoluteDateTime({
    date,
    preset,
    locale: resolvedLocale,
    includeSeconds,
    hourCycle,
  })
}

export function getDateTimePresetPreview(
  preset: DateTimePreset,
  {
    hourCycle = "24h",
    includeSeconds = false,
    locale,
  }: {
    hourCycle?: HourCyclePreference
    includeSeconds?: boolean
    locale?: string
  } = {},
) {
  return formatDateTimeWithPreset(PREVIEW_SAMPLE, {
    preset,
    hourCycle,
    includeSeconds,
    fallback: "-",
    locale,
  })
}
