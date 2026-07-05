import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import {
  type PlayerDisplayRatingIconScope,
  usePlayerDisplayPreferences,
} from "@/components/player-display-preferences-provider"
import { type Theme, useTheme } from "@/components/theme-provider"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import useAuth from "@/hooks/useAuth"
import {
  type DateTimePreset,
  getDateTimePresetOptions,
  getDateTimePresetPreview,
  getHourCycleOptions,
  type HourCyclePreference,
} from "@/lib/date-time"
import {
  DEFAULT_PAGE_OPTIONS,
  type DefaultPagePreference,
  readDefaultPagePreference,
  writeDefaultPagePreference,
} from "@/lib/default-page"

const PREVIEW_SAMPLE = new Date(2026, 2, 22, 14, 5, 9)

export default function AppearanceSettings() {
  const { t } = useTranslation()
  const { user: currentUser } = useAuth()
  const { formatDateTime, hourCycle, preset, setHourCycle, setPreset } =
    useDateTimeFormat()
  const {
    ratingIconScope,
    setRatingIconScope,
    setShowCountryFlag,
    setShowRatingIcon,
    showCountryFlag,
    showRatingIcon,
  } = usePlayerDisplayPreferences()
  const { resolvedTheme, setTheme, theme } = useTheme()
  const [defaultPage, setDefaultPage] = useState<DefaultPagePreference>(
    readDefaultPagePreference,
  )
  const themeOptions = useMemo<
    Array<{
      value: Theme
      label: string
    }>
  >(
    () => [
      {
        value: "light",
        label: t("theme.light"),
      },
      {
        value: "dark",
        label: t("theme.dark"),
      },
      {
        value: "system",
        label: t("theme.system"),
      },
    ],
    [t],
  )
  const ratingIconScopeOptions = useMemo<
    Array<{
      value: PlayerDisplayRatingIconScope
      label: string
    }>
  >(
    () => [
      {
        value: "primary",
        label: t("settings.appearance.ratingIconScopes.primary"),
      },
      {
        value: "global",
        label: t("settings.appearance.ratingIconScopes.global"),
      },
    ],
    [t],
  )
  const defaultPageOptions = useMemo<
    Array<{
      value: DefaultPagePreference
      label: string
    }>
  >(
    () =>
      DEFAULT_PAGE_OPTIONS.map((value) => ({
        value,
        label: t(`settings.appearance.defaultPages.${value.slice(1)}`),
      })),
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

  const selectedHourCycle = useMemo(
    () =>
      hourCycleOptions.find((option) => option.value === hourCycle) ??
      hourCycleOptions[0],
    [hourCycle, hourCycleOptions],
  )
  const previewPlayer = currentUser
    ? {
        steamid64: currentUser.steamid64,
        displayName: currentUser.player?.display_name ?? null,
      }
    : null

  return (
    <div className="grid gap-6 max-w-3xl">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.appearance.playerDisplayTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <p className="text-sm font-medium">
                {t("settings.appearance.countryFlag")}
              </p>
            </div>
            <Switch
              checked={showCountryFlag}
              onCheckedChange={setShowCountryFlag}
              aria-label={t("settings.appearance.countryFlag")}
              data-testid="appearance-player-country-flag-switch"
            />
          </div>

          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <p className="text-sm font-medium">
                {t("settings.appearance.ratingIcon")}
              </p>
            </div>
            <Switch
              checked={showRatingIcon}
              onCheckedChange={setShowRatingIcon}
              aria-label={t("settings.appearance.ratingIcon")}
              data-testid="appearance-player-rating-icon-switch"
            />
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">
              {t("settings.appearance.ratingIconScope")}
            </p>
            <Select
              value={ratingIconScope}
              onValueChange={(value) =>
                setRatingIconScope(value as PlayerDisplayRatingIconScope)
              }
            >
              <SelectTrigger
                className="w-full sm:w-[22rem]"
                data-testid="appearance-player-rating-scope-select"
              >
                <SelectValue
                  placeholder={t("settings.appearance.selectRatingIconScope")}
                />
              </SelectTrigger>
              <SelectContent>
                {ratingIconScopeOptions.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    data-testid={`appearance-player-rating-scope-option-${option.value}`}
                  >
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">
              {t("settings.appearance.playerDisplayPreview")}
            </p>
            <div
              className="w-full rounded-lg border border-border/70 bg-background/70 px-4 py-3"
              data-testid="appearance-player-display-preview"
            >
              {previewPlayer ? (
                <PlayerDisplay
                  player={previewPlayer}
                  disableProfileLink
                  className="min-w-0"
                />
              ) : (
                <p className="text-sm text-muted-foreground">
                  {t("settings.appearance.playerDisplayPreviewUnavailable")}
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("settings.appearance.themeTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">
              {t("settings.appearance.defaultPage")}
            </p>
            <Select
              value={defaultPage}
              onValueChange={(value) => {
                const nextDefaultPage = value as DefaultPagePreference
                setDefaultPage(nextDefaultPage)
                writeDefaultPagePreference(nextDefaultPage)
              }}
            >
              <SelectTrigger
                className="w-full sm:w-72"
                data-testid="appearance-default-page-select"
              >
                <SelectValue
                  placeholder={t("settings.appearance.selectDefaultPage")}
                />
              </SelectTrigger>
              <SelectContent>
                {defaultPageOptions.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    data-testid={`appearance-default-page-option-${option.value.slice(1)}`}
                  >
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

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
            <p data-testid="appearance-datetime-preview-default">
              {t("settings.appearance.recordTimestamp")}:{" "}
              <span className="font-medium text-foreground">
                {formatDateTime(PREVIEW_SAMPLE, { fallback: "-" })}
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
