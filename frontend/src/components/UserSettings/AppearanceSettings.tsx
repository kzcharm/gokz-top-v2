import { useMemo } from "react"
import { useTranslation } from "react-i18next"

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
  type DateTimePreset,
  getDateTimePresetOptions,
  getDateTimePresetPreview,
  getHourCycleOptions,
  type HourCyclePreference,
} from "@/lib/date-time"

const PREVIEW_SAMPLE = new Date(2026, 2, 22, 14, 5, 9)

export default function AppearanceSettings() {
  const { t } = useTranslation()
  const { formatDateTime, hourCycle, preset, setHourCycle, setPreset } =
    useDateTimeFormat()
  const { resolvedTheme, setTheme, theme } = useTheme()
  const themeOptions = useMemo<
    Array<{
      value: Theme
      label: string
      description: string
    }>
  >(
    () => [
      {
        value: "light",
        label: t("theme.light"),
        description: t("settings.appearance.themeDescriptions.light"),
      },
      {
        value: "dark",
        label: t("theme.dark"),
        description: t("settings.appearance.themeDescriptions.dark"),
      },
      {
        value: "system",
        label: t("theme.system"),
        description: t("settings.appearance.themeDescriptions.system"),
      },
    ],
    [t],
  )
  const dateTimePresetOptions = getDateTimePresetOptions()
  const hourCycleOptions = getHourCycleOptions()

  const selectedPreset = useMemo(
    () =>
      dateTimePresetOptions.find((option) => option.value === preset) ??
      dateTimePresetOptions[0],
    [dateTimePresetOptions, preset],
  )

  const selectedTheme = useMemo(
    () =>
      themeOptions.find((option) => option.value === theme) ?? themeOptions[0],
    [theme, themeOptions],
  )
  const selectedHourCycle = useMemo(
    () =>
      hourCycleOptions.find((option) => option.value === hourCycle) ??
      hourCycleOptions[0],
    [hourCycle, hourCycleOptions],
  )

  return (
    <div className="grid gap-6 max-w-3xl">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.appearance.themeTitle")}</CardTitle>
          <CardDescription>
            {t("settings.appearance.themeDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">
              {t("settings.appearance.colorTheme")}
            </p>
            <Select
              value={theme}
              onValueChange={(value) => setTheme(value as Theme)}
            >
              <SelectTrigger
                className="w-full sm:w-72"
                data-testid="appearance-theme-select"
              >
                <SelectValue
                  placeholder={t("settings.appearance.selectTheme")}
                />
              </SelectTrigger>
              <SelectContent>
                {themeOptions.map((option) => (
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
              {t("settings.appearance.activeTheme")}:{" "}
              <span className="font-medium text-foreground capitalize">
                {resolvedTheme}
              </span>
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("settings.appearance.dateTimeTitle")}</CardTitle>
          <CardDescription>
            {t("settings.appearance.dateTimeDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">
              {t("settings.appearance.formatter")}
            </p>
            <Select
              value={preset}
              onValueChange={(value) => setPreset(value as DateTimePreset)}
            >
              <SelectTrigger
                className="w-full sm:w-72"
                data-testid="appearance-datetime-preset-select"
              >
                <SelectValue
                  placeholder={t("settings.appearance.selectDateTimeFormat")}
                >
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
                {dateTimePresetOptions.map((option) => (
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
            <p className="text-sm font-medium">
              {t("settings.appearance.timeFormat")}
            </p>
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
                <SelectValue
                  placeholder={t("settings.appearance.selectTimeFormat")}
                >
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
                {hourCycleOptions.map((option) => (
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
              {t("settings.appearance.recordTimestamp")}:{" "}
              <span className="font-medium text-foreground">
                {formatDateTime(PREVIEW_SAMPLE, { fallback: "-" })}
              </span>
            </p>
            <p data-testid="appearance-datetime-preview-seconds">
              {t("settings.appearance.updateTimestamp")}:{" "}
              <span className="font-medium text-foreground">
                {formatDateTime(PREVIEW_SAMPLE, {
                  fallback: "-",
                  includeSeconds: true,
                })}
              </span>
            </p>
            <p data-testid="appearance-datetime-preview-relative">
              {t("settings.appearance.relativeTimestamp")}:{" "}
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
