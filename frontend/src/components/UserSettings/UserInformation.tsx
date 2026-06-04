import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CircleHelp, LogOut, Pencil, Save } from "lucide-react"
import { type ReactNode, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { MeService, type ModeScope, type PlayerSettingsPublic } from "@/client"
import { CountryFlag, getCountryName } from "@/components/Common/CountryFlag"
import { CountryPicker } from "@/components/Common/CountryPicker"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { getScopeTone, SCOPE_OPTIONS } from "@/components/Common/ScopeSelector"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
import { extractErrorMessage } from "@/utils"

type FieldStatus = PlayerSettingsPublic["alias"]

const aliasPattern = /^[A-Za-z0-9 _-]+$/
const customIdAllowedPattern = /^[A-Za-z0-9_-]+$/
const customIdLetterPattern = /[A-Za-z]/

function validateAliasInput(
  alias: string,
  t: (key: string) => string,
): string | null {
  if (!aliasPattern.test(alias)) {
    return t("settings.profile.errors.aliasInvalidChars")
  }

  return null
}

function validateCustomIdInput(
  customId: string,
  t: (key: string) => string,
): string | null {
  if (!customIdAllowedPattern.test(customId)) {
    return t("settings.profile.errors.customIdInvalidChars")
  }

  if (!customIdLetterPattern.test(customId)) {
    return t("settings.profile.errors.customIdMissingLetter")
  }

  return null
}

function FieldHint({
  status,
  locked,
  availableLabel,
  soonFallback,
}: {
  status: FieldStatus
  locked?: boolean
  availableLabel: string
  soonFallback: string
}) {
  if (locked) {
    return null
  }

  if (!status.can_change && status.next_available_at) {
    return (
      <p className="text-xs text-muted-foreground">
        {availableLabel}{" "}
        <FormattedDateTime
          value={status.next_available_at}
          display="contextual-relative"
          fallback={soonFallback}
        />
      </p>
    )
  }

  return null
}

const settingsQueryKey = ["player-settings"]

function AliasLabel({
  label,
  tooltip,
  ariaLabel,
}: {
  label: string
  tooltip: string
  ariaLabel: string
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span>{label}</span>
      <Tooltip delayDuration={150}>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="text-muted-foreground transition-colors hover:text-foreground"
            aria-label={ariaLabel}
          >
            <CircleHelp className="size-4" />
          </button>
        </TooltipTrigger>
        <TooltipContent sideOffset={8} className="max-w-64">
          {tooltip}
        </TooltipContent>
      </Tooltip>
    </span>
  )
}

function ReadonlyField({
  label,
  labelNode,
  value,
  valueClassName,
}: {
  label: string
  labelNode?: ReactNode
  value: string
  valueClassName?: string
}) {
  return (
    <div className="space-y-1">
      <p className="text-sm text-muted-foreground">{labelNode ?? label}</p>
      <p className={valueClassName ?? "font-medium"}>{value}</p>
    </div>
  )
}

function ReadonlyCountryField({
  label,
  countryCode,
  countryName,
}: {
  label: string
  countryCode: string | null
  countryName: string
}) {
  return (
    <div className="space-y-1">
      <p className="text-sm text-muted-foreground">{label}</p>
      <div className="flex items-center gap-2 font-medium">
        <CountryFlag countryCode={countryCode} showTooltip={false} />
        <span>{countryName}</span>
      </div>
    </div>
  )
}

const UserInformation = () => {
  const { t, i18n } = useTranslation()
  const { user: currentUser, logout } = useAuth()
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [aliasInput, setAliasInput] = useState("")
  const [customIdInput, setCustomIdInput] = useState("")
  const [countryInput, setCountryInput] = useState<string | null>(null)
  const [primaryScopeInput, setPrimaryScopeInput] = useState<ModeScope>("OVR")
  const [isEditing, setIsEditing] = useState(false)

  const settingsQuery = useQuery({
    queryKey: settingsQueryKey,
    enabled: Boolean(currentUser),
    queryFn: () => MeService.readCurrentPlayerSettings(),
    staleTime: 60_000,
  })

  const settings = settingsQuery.data
  const player = settings?.player

  useEffect(() => {
    if (!player) {
      return
    }

    setAliasInput(player.alias ?? "")
    setCustomIdInput(player.custom_id ?? "")
    setCountryInput(player.country ?? null)
    setPrimaryScopeInput(player.primary_scope ?? "OVR")
    setIsEditing(false)
  }, [player])

  const initialValues = useMemo(
    () => ({
      alias: player?.alias ?? "",
      customId: player?.custom_id ?? "",
      country: player?.country ?? null,
      primaryScope: player?.primary_scope ?? "OVR",
    }),
    [player],
  )

  const dirty =
    aliasInput !== initialValues.alias ||
    customIdInput !== initialValues.customId ||
    countryInput !== initialValues.country ||
    primaryScopeInput !== initialValues.primaryScope

  const mutation = useMutation({
    mutationFn: () => {
      const requestBody: {
        alias?: string
        custom_id?: string
        country?: string
        primary_scope?: ModeScope
      } = {}
      const alias = aliasInput.trim()
      const customId = customIdInput.trim()

      if (aliasInput !== initialValues.alias) {
        if (!alias) {
          throw new Error(t("settings.profile.errors.aliasBlank"))
        }
        const aliasValidationError = validateAliasInput(alias, t)
        if (aliasValidationError) {
          throw new Error(aliasValidationError)
        }
        requestBody.alias = alias
      }

      if (customIdInput !== initialValues.customId) {
        if (!customId) {
          throw new Error(t("settings.profile.errors.customIdBlank"))
        }
        const customIdValidationError = validateCustomIdInput(customId, t)
        if (customIdValidationError) {
          throw new Error(customIdValidationError)
        }
        requestBody.custom_id = customId
      }

      if (countryInput !== initialValues.country) {
        if (!countryInput) {
          throw new Error(t("settings.profile.errors.countryCleared"))
        }
        requestBody.country = countryInput
      }

      if (primaryScopeInput !== initialValues.primaryScope) {
        requestBody.primary_scope = primaryScopeInput
      }

      return MeService.updateCurrentPlayerSettings({ requestBody })
    },
    onSuccess: (data) => {
      queryClient.setQueryData(settingsQueryKey, data)
      setIsEditing(false)
      showSuccessToast(t("settings.profile.toast.updated"))
    },
    onError: (error) => {
      showErrorToast(extractErrorMessage(error))
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: settingsQueryKey })
      void queryClient.invalidateQueries({ queryKey: ["currentUser"] })
      void queryClient.invalidateQueries({ queryKey: ["sidebar-user-player"] })
      void queryClient.invalidateQueries({ queryKey: ["profile-player"] })
      void queryClient.invalidateQueries({ queryKey: ["graphql", "player"] })
      void queryClient.invalidateQueries({
        queryKey: ["leaderboards", "players"],
      })
    },
  })

  if (!currentUser) {
    return null
  }

  const aliasDisabled =
    !isEditing || settings?.alias.can_change === false || mutation.isPending
  const customIdDisabled =
    !isEditing || settings?.custom_id.can_change === false || mutation.isPending
  const countryDisabled = !isEditing || mutation.isPending
  const primaryScopeDisabled = !isEditing || mutation.isPending
  const countryDisplayName =
    getCountryName(countryInput, i18n.resolvedLanguage) ??
    t("common.unknownCountry")
  const selectedPrimaryScope =
    SCOPE_OPTIONS.find((option) => option.value === primaryScopeInput) ??
    SCOPE_OPTIONS[0]
  const profileDisplayPlayer = player ?? {
    steamid64: currentUser.steamid64,
    display_name: currentUser.player?.display_name ?? null,
  }

  return (
    <Card className="max-w-2xl">
      <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-3">
          <CardTitle>{t("settings.profile.title")}</CardTitle>
          <PlayerDisplay player={profileDisplayPlayer} className="min-w-0" />
        </div>
        {isEditing ? (
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={mutation.isPending}
              onClick={() => {
                setAliasInput(initialValues.alias)
                setCustomIdInput(initialValues.customId)
                setCountryInput(initialValues.country)
                setPrimaryScopeInput(initialValues.primaryScope)
                setIsEditing(false)
              }}
            >
              {t("settings.profile.actions.cancel")}
            </Button>
            <LoadingButton
              type="submit"
              form="user-settings-form"
              loading={mutation.isPending}
              disabled={!dirty || settingsQuery.isLoading}
            >
              <Save className="size-4" />
              {t("settings.profile.actions.save")}
            </LoadingButton>
          </div>
        ) : (
          <Button
            type="button"
            variant="outline"
            disabled={settingsQuery.isLoading}
            onClick={() => setIsEditing(true)}
          >
            <Pencil className="size-4" />
            {t("settings.profile.actions.edit")}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <form
          id="user-settings-form"
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault()
            mutation.mutate()
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-sm text-muted-foreground">
                {t("settings.profile.fields.steamName")}
              </p>
              <p className="font-medium">
                {player?.name ?? t("settings.profile.fallbacks.notSet")}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">
                {t("settings.profile.fields.steamId64")}
              </p>
              <p className="font-mono text-sm">{currentUser.steamid64}</p>
            </div>
          </div>

          {isEditing ? (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label
                    htmlFor="settings-alias"
                    className="inline-flex items-center text-sm font-medium"
                  >
                    <AliasLabel
                      label={t("settings.profile.fields.alias")}
                      tooltip={t("settings.profile.aliasInfo")}
                      ariaLabel={t("settings.profile.aliasInfoAria")}
                    />
                  </label>
                  <Input
                    id="settings-alias"
                    value={aliasInput}
                    maxLength={25}
                    disabled={aliasDisabled}
                    placeholder={t("settings.profile.placeholders.alias")}
                    onChange={(event) => setAliasInput(event.target.value)}
                  />
                  {settings ? (
                    <FieldHint
                      status={settings.alias}
                      availableLabel={t("settings.profile.available")}
                      soonFallback={t("settings.profile.soon")}
                    />
                  ) : null}
                </div>

                <div className="space-y-2">
                  <label
                    htmlFor="settings-custom-id"
                    className="text-sm font-medium"
                  >
                    {t("settings.profile.fields.customId")}
                  </label>
                  <Input
                    id="settings-custom-id"
                    value={customIdInput}
                    maxLength={25}
                    disabled={customIdDisabled}
                    placeholder={t("settings.profile.placeholders.customId")}
                    onChange={(event) => setCustomIdInput(event.target.value)}
                  />
                  {settings ? (
                    <FieldHint
                      status={settings.custom_id}
                      availableLabel={t("settings.profile.available")}
                      soonFallback={t("settings.profile.soon")}
                    />
                  ) : null}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <span className="text-sm font-medium">
                    {t("settings.profile.fields.countryRegion")}
                  </span>
                  <CountryPicker
                    value={countryInput}
                    onChange={setCountryInput}
                    placeholder={t("settings.profile.placeholders.country")}
                    clearLabel={t("settings.profile.clearCountry")}
                    disabled={countryDisabled}
                  />
                  {settings ? (
                    <FieldHint
                      status={settings.country}
                      locked={settings.country_locked}
                      availableLabel={t("settings.profile.available")}
                      soonFallback={t("settings.profile.soon")}
                    />
                  ) : null}
                </div>

                <div className="space-y-2">
                  <span className="text-sm font-medium">
                    {t("settings.profile.fields.primaryScope")}
                  </span>
                  <Select
                    value={primaryScopeInput}
                    onValueChange={(value) =>
                      setPrimaryScopeInput(value as ModeScope)
                    }
                    disabled={primaryScopeDisabled}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue
                        placeholder={t(
                          "settings.profile.placeholders.primaryScope",
                        )}
                      >
                        <span
                          className={`inline-flex min-w-12 items-center justify-center rounded-md px-2 py-0.5 font-mono text-xs font-semibold tracking-[0.16em] ${getScopeTone(selectedPrimaryScope.value)}`}
                        >
                          {selectedPrimaryScope.value}
                        </span>
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {SCOPE_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          <span
                            className={`inline-flex min-w-12 items-center justify-center rounded-md px-2 py-0.5 font-mono text-xs font-semibold tracking-[0.16em] ${option.toneClassName}`}
                          >
                            {option.value}
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </>
          ) : (
            <div className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <ReadonlyField
                  value={aliasInput || t("settings.profile.fallbacks.notSet")}
                  label={t("settings.profile.fields.alias")}
                  labelNode={
                    <AliasLabel
                      label={t("settings.profile.fields.alias")}
                      tooltip={t("settings.profile.aliasInfo")}
                      ariaLabel={t("settings.profile.aliasInfoAria")}
                    />
                  }
                />
                <ReadonlyField
                  value={
                    customIdInput || t("settings.profile.fallbacks.notSet")
                  }
                  label={t("settings.profile.fields.customId")}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <ReadonlyCountryField
                  label={t("settings.profile.fields.countryRegion")}
                  countryCode={countryInput}
                  countryName={countryDisplayName}
                />
                <ReadonlyField
                  value={primaryScopeInput}
                  label={t("settings.profile.fields.primaryScope")}
                  valueClassName={cn(
                    "inline-flex min-w-12 items-center justify-center rounded-md px-2 py-0.5 font-mono text-xs font-semibold tracking-[0.16em]",
                    getScopeTone(primaryScopeInput),
                  )}
                />
              </div>
            </div>
          )}
        </form>
        <div className="mt-6 flex justify-end border-border border-t pt-5">
          <Button
            type="button"
            variant="destructive"
            onClick={logout}
            data-testid="settings-profile-logout-button"
          >
            <LogOut className="size-4" />
            {t("auth.logout")}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default UserInformation
