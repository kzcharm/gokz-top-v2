import { getLocale, translate } from "@/i18n/locale"

export type DateTimePreset = "iso" | "us" | "euro" | "long"

export type DateTimeDisplay = "absolute" | "relative" | "contextual-relative"

export type HourCyclePreference = "24h" | "12h"

export type DateTimeFormatOptions = {
  includeSeconds?: boolean
  dateOnly?: boolean
  display?: DateTimeDisplay
  fallback?: string
  locale?: string
  hourCycle?: HourCyclePreference
}

export const DATE_TIME_FORMAT_STORAGE_KEY = "gokz-datetime-format"
export const HOUR_CYCLE_STORAGE_KEY = "gokz-hour-cycle"

const PREVIEW_SAMPLE = new Date(2026, 2, 22, 14, 5, 9)

export function getBrowserLocale() {
  return getLocale()
}

export function isDateTimePreset(
  value: string | null,
): value is DateTimePreset {
  return (
    value === "iso" || value === "us" || value === "euro" || value === "long"
  )
}

export function isHourCyclePreference(
  value: string | null,
): value is HourCyclePreference {
  return value === "24h" || value === "12h"
}

export function getDateTimePresetOptions(): Array<{
  value: DateTimePreset
  label: string
  description: string
}> {
  return [
    {
      value: "iso",
      label: translate("dateTime.presets.iso.label"),
      description: translate("dateTime.presets.iso.description"),
    },
    {
      value: "us",
      label: translate("dateTime.presets.us.label"),
      description: translate("dateTime.presets.us.description"),
    },
    {
      value: "euro",
      label: translate("dateTime.presets.euro.label"),
      description: translate("dateTime.presets.euro.description"),
    },
    {
      value: "long",
      label: translate("dateTime.presets.long.label"),
      description: translate("dateTime.presets.long.description"),
    },
  ]
}

export function getHourCycleOptions(): Array<{
  value: HourCyclePreference
  label: string
  description: string
}> {
  return [
    {
      value: "24h",
      label: translate("dateTime.hourCycle.h24.label"),
      description: translate("dateTime.hourCycle.h24.description"),
    },
    {
      value: "12h",
      label: translate("dateTime.hourCycle.h12.label"),
      description: translate("dateTime.hourCycle.h12.description"),
    },
  ]
}

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

function getIsoLikeTime(
  date: Date,
  includeSeconds: boolean,
  hourCycle: HourCyclePreference,
) {
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
  dateOnly: boolean,
  hourCycle: HourCyclePreference,
) {
  const year = date.getFullYear()
  const month = padNumber(date.getMonth() + 1)
  const day = padNumber(date.getDate())
  if (dateOnly) {
    return `${year}-${month}-${day}`
  }

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

function formatTimeOnly({
  date,
  locale,
  includeSeconds,
  hourCycle,
}: {
  date: Date
  locale: string
  includeSeconds: boolean
  hourCycle: HourCyclePreference
}) {
  return new Intl.DateTimeFormat(locale, {
    ...getIntlHourOptions(includeSeconds, hourCycle),
  }).format(date)
}

function formatAbsoluteDateTime({
  date,
  preset,
  locale,
  includeSeconds,
  dateOnly,
  hourCycle,
}: {
  date: Date
  preset: DateTimePreset
  locale: string
  includeSeconds: boolean
  dateOnly: boolean
  hourCycle: HourCyclePreference
}) {
  switch (preset) {
    case "iso":
      return formatIsoLike(date, includeSeconds, dateOnly, hourCycle)
    case "us":
      return new Intl.DateTimeFormat("en-US", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        ...(dateOnly ? {} : getIntlHourOptions(includeSeconds, hourCycle)),
      }).format(date)
    case "euro":
      return new Intl.DateTimeFormat("en-GB", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        ...(dateOnly ? {} : getIntlHourOptions(includeSeconds, hourCycle)),
      }).format(date)
    default:
      return new Intl.DateTimeFormat(locale, {
        year: "numeric",
        month: "long",
        day: "numeric",
        ...(dateOnly ? {} : getIntlHourOptions(includeSeconds, hourCycle)),
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
      const value = Math.max(
        1,
        Math.floor(absoluteDiff / relativeUnit.sizeInMs),
      )
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

function formatRelativeTimeTranslationKey(
  value: number,
  unit: SupportedRelativeUnit,
  isPast: boolean,
) {
  const key = isPast
    ? `dateTime.relative.${unit}`
    : `dateTime.relative.in${unit[0].toUpperCase()}${unit.slice(1)}`

  return translate(key, { count: value })
}

function formatRelativeDateTime(date: Date, locale: string) {
  const diffInMs = date.getTime() - Date.now()
  const isPast = diffInMs < 0
  const { unit, value } = getRelativeUnit(diffInMs)

  if (locale.toLowerCase().startsWith("en")) {
    return formatRelativeTimeTranslationKey(value, unit, isPast)
  }

  const formatter = new Intl.RelativeTimeFormat(locale, {
    numeric: "always",
    style: "short",
  })

  return formatter.format(isPast ? -value : value, unit)
}

function isSameLocalDay(left: Date, right: Date) {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  )
}

function formatContextualRelativeDateTime({
  date,
  locale,
  preset,
  hourCycle,
}: {
  date: Date
  locale: string
  preset: DateTimePreset
  hourCycle: HourCyclePreference
}) {
  const now = new Date()
  const diffInMs = now.getTime() - date.getTime()

  if (diffInMs < 0) {
    return formatRelativeDateTime(date, locale)
  }

  if (diffInMs < MINUTE_IN_MS) {
    const seconds = Math.max(1, Math.floor(diffInMs / SECOND_IN_MS))
    return translate("dateTime.relative.second", { count: seconds })
  }

  if (diffInMs < HOUR_IN_MS) {
    const minutes = Math.floor(diffInMs / MINUTE_IN_MS)
    return translate("dateTime.relative.minute", { count: minutes })
  }

  if (diffInMs < 2 * HOUR_IN_MS) {
    const minutes = Math.floor((diffInMs - HOUR_IN_MS) / MINUTE_IN_MS)
    return translate("dateTime.relative.oneHourMinutesAgo", { minutes })
  }

  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const formattedTime = formatTimeOnly({
    date,
    locale,
    includeSeconds: false,
    hourCycle,
  })

  if (isSameLocalDay(date, now)) {
    return translate("dateTime.relative.todayAt", { time: formattedTime })
  }

  if (isSameLocalDay(date, yesterday)) {
    return translate("dateTime.relative.yesterdayAt", { time: formattedTime })
  }

  return formatAbsoluteDateTime({
    date,
    preset,
    locale,
    includeSeconds: false,
    dateOnly: false,
    hourCycle,
  })
}

export function formatDateTimeWithPreset(
  value: string | Date | null | undefined,
  {
    preset,
    hourCycle = "24h",
    includeSeconds = false,
    dateOnly = false,
    display = "absolute",
    fallback = translate("common.unknown"),
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

  if (display === "contextual-relative") {
    return formatContextualRelativeDateTime({
      date,
      locale: resolvedLocale,
      preset,
      hourCycle,
    })
  }

  return formatAbsoluteDateTime({
    date,
    preset,
    locale: resolvedLocale,
    includeSeconds,
    dateOnly,
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
