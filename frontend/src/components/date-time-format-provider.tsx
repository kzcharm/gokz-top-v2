import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react"

import {
  DATE_TIME_FORMAT_STORAGE_KEY,
  HOUR_CYCLE_STORAGE_KEY,
  formatDateTimeWithPreset,
  getBrowserLocale,
  isDateTimePreset,
  isHourCyclePreference,
  type DateTimeFormatOptions,
  type DateTimePreset,
  type HourCyclePreference,
} from "@/lib/date-time"

type DateTimeFormatProviderProps = {
  children: React.ReactNode
  defaultPreset?: DateTimePreset
  presetStorageKey?: string
  defaultHourCycle?: HourCyclePreference
  hourCycleStorageKey?: string
}

type DateTimeFormatProviderState = {
  preset: DateTimePreset
  setPreset: (preset: DateTimePreset) => void
  hourCycle: HourCyclePreference
  setHourCycle: (hourCycle: HourCyclePreference) => void
  formatDateTime: (
    value: string | Date | null | undefined,
    options?: DateTimeFormatOptions,
  ) => string
}

const initialState: DateTimeFormatProviderState = {
  preset: "iso",
  setPreset: () => null,
  hourCycle: "24h",
  setHourCycle: () => null,
  formatDateTime: () => "Unknown",
}

const DateTimeFormatProviderContext =
  createContext<DateTimeFormatProviderState>(initialState)

export function DateTimeFormatProvider({
  children,
  defaultPreset = "iso",
  presetStorageKey = DATE_TIME_FORMAT_STORAGE_KEY,
  defaultHourCycle = "24h",
  hourCycleStorageKey = HOUR_CYCLE_STORAGE_KEY,
}: DateTimeFormatProviderProps) {
  const [preset, setPresetState] = useState<DateTimePreset>(
    () => {
      const storedPreset = localStorage.getItem(presetStorageKey)
      return isDateTimePreset(storedPreset) ? storedPreset : defaultPreset
    },
  )
  const [hourCycle, setHourCycleState] = useState<HourCyclePreference>(() => {
    const storedHourCycle = localStorage.getItem(hourCycleStorageKey)
    return isHourCyclePreference(storedHourCycle)
      ? storedHourCycle
      : defaultHourCycle
  })

  const setPreset = useCallback(
    (nextPreset: DateTimePreset) => {
      localStorage.setItem(presetStorageKey, nextPreset)
      setPresetState(nextPreset)
    },
    [presetStorageKey],
  )

  const setHourCycle = useCallback(
    (nextHourCycle: HourCyclePreference) => {
      localStorage.setItem(hourCycleStorageKey, nextHourCycle)
      setHourCycleState(nextHourCycle)
    },
    [hourCycleStorageKey],
  )

  const formatDateTime = useCallback(
    (
      value: string | Date | null | undefined,
      options: DateTimeFormatOptions = {},
    ) =>
      formatDateTimeWithPreset(value, {
        preset,
        hourCycle,
        locale: options.locale ?? getBrowserLocale(),
        ...options,
      }),
    [hourCycle, preset],
  )

  const value = useMemo(
    () => ({
      preset,
      setPreset,
      hourCycle,
      setHourCycle,
      formatDateTime,
    }),
    [formatDateTime, hourCycle, preset, setHourCycle, setPreset],
  )

  return (
    <DateTimeFormatProviderContext.Provider value={value}>
      {children}
    </DateTimeFormatProviderContext.Provider>
  )
}

export function useDateTimeFormat() {
  const context = useContext(DateTimeFormatProviderContext)

  if (context === undefined) {
    throw new Error(
      "useDateTimeFormat must be used within a DateTimeFormatProvider",
    )
  }

  return context
}
