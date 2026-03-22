import { useMemo } from "react"

import { useDateTimeFormat } from "@/components/date-time-format-provider"
import { type Theme, useTheme } from "@/components/theme-provider"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  DATE_TIME_PRESET_OPTIONS,
  type DateTimePreset,
  getDateTimePresetPreview,
  HOUR_CYCLE_OPTIONS,
  type HourCyclePreference,
} from "@/lib/date-time"

const THEME_OPTIONS: Array<{
  value: Theme
  label: string
  description: string
}> = [
  {
    value: "light",
    label: "Light",
    description: "Always use the light theme.",
  },
  {
    value: "dark",
    label: "Dark",
    description: "Always use the dark theme.",
  },
  {
    value: "system",
    label: "System",
    description: "Follow your device theme automatically.",
  },
]

const PREVIEW_SAMPLE = new Date(2026, 2, 22, 14, 5, 9)

export default function AppearanceSettings() {
  const { formatDateTime, hourCycle, preset, setHourCycle, setPreset } =
    useDateTimeFormat()
  const { resolvedTheme, setTheme, theme } = useTheme()

  const selectedPreset = useMemo(
    () =>
      DATE_TIME_PRESET_OPTIONS.find((option) => option.value === preset) ??
      DATE_TIME_PRESET_OPTIONS[0],
    [preset],
  )

  const selectedTheme = useMemo(
    () =>
      THEME_OPTIONS.find((option) => option.value === theme) ?? THEME_OPTIONS[0],
    [theme],
  )
  const selectedHourCycle = useMemo(
    () =>
      HOUR_CYCLE_OPTIONS.find((option) => option.value === hourCycle) ??
      HOUR_CYCLE_OPTIONS[0],
    [hourCycle],
  )

  return (
    <div className="grid gap-6 max-w-3xl">
      <Card>
        <CardHeader>
          <CardTitle>Theme</CardTitle>
          <CardDescription>
            Choose how the application should look on this browser.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">Color theme</p>
            <Select value={theme} onValueChange={(value) => setTheme(value as Theme)}>
              <SelectTrigger
                className="w-full sm:w-72"
                data-testid="appearance-theme-select"
              >
                <SelectValue placeholder="Select theme" />
              </SelectTrigger>
              <SelectContent>
                {THEME_OPTIONS.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    data-testid={`appearance-theme-option-${option.value}`}
                  >
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 text-sm text-muted-foreground">
            <p>{selectedTheme.description}</p>
            <p>
              Active theme:{" "}
              <span className="font-medium text-foreground capitalize">
                {resolvedTheme}
              </span>
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Date and time</CardTitle>
          <CardDescription>
            Control the default timestamp style for this browser. Seconds and
            relative time remain per-view decisions.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">Datetime formatter</p>
            <Select
              value={preset}
              onValueChange={(value) => setPreset(value as DateTimePreset)}
            >
              <SelectTrigger
                className="w-full sm:w-72"
                data-testid="appearance-datetime-preset-select"
              >
                <SelectValue placeholder="Select datetime format">
                  <span className="flex items-center justify-between gap-4 w-full">
                    <span>{selectedPreset.label}</span>
                    <span className="text-xs text-muted-foreground">
                      {getDateTimePresetPreview(selectedPreset.value, {
                        hourCycle,
                      })}
                    </span>
                  </span>
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {DATE_TIME_PRESET_OPTIONS.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    data-testid={`appearance-datetime-preset-option-${option.value}`}
                  >
                    <span className="flex min-w-0 flex-col">
                      <span>{option.label}</span>
                      <span className="text-xs text-muted-foreground">
                        {getDateTimePresetPreview(option.value, { hourCycle })}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <p className="text-sm font-medium">Time format</p>
            <Select
              value={hourCycle}
              onValueChange={(value) =>
                setHourCycle(value as HourCyclePreference)
              }
            >
              <SelectTrigger
                className="w-full sm:w-72"
                data-testid="appearance-hour-cycle-select"
              >
                <SelectValue placeholder="Select time format">
                  <span className="flex items-center justify-between gap-4 w-full">
                    <span>{selectedHourCycle.label}</span>
                    <span className="text-xs text-muted-foreground">
                      {getDateTimePresetPreview(preset, {
                        hourCycle: selectedHourCycle.value,
                      })}
                    </span>
                  </span>
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {HOUR_CYCLE_OPTIONS.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    data-testid={`appearance-hour-cycle-option-${option.value}`}
                  >
                    <span className="flex min-w-0 flex-col">
                      <span>{option.label}</span>
                      <span className="text-xs text-muted-foreground">
                        {getDateTimePresetPreview(preset, {
                          hourCycle: option.value,
                        })}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 text-sm text-muted-foreground">
            <p>{selectedPreset.description}</p>
            <p>{selectedHourCycle.description}</p>
            <p data-testid="appearance-datetime-preview-default">
              Record timestamp:{" "}
              <span className="font-medium text-foreground">
                {formatDateTime(PREVIEW_SAMPLE, { fallback: "-" })}
              </span>
            </p>
            <p data-testid="appearance-datetime-preview-seconds">
              Update timestamp:{" "}
              <span className="font-medium text-foreground">
                {formatDateTime(PREVIEW_SAMPLE, {
                  fallback: "-",
                  includeSeconds: true,
                })}
              </span>
            </p>
            <p data-testid="appearance-datetime-preview-relative">
              Relative timestamp:{" "}
              <span className="font-medium text-foreground">
                {formatDateTime(new Date(Date.now() - 65 * 60 * 1000), {
                  display: "relative",
                  fallback: "-",
                })}
              </span>
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
