import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pencil, Save } from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import { type PlayerSettingsPublic, PlayersService } from "@/client"
import { CountryPicker } from "@/components/Common/CountryPicker"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { extractErrorMessage } from "@/utils"

type FieldStatus = PlayerSettingsPublic["alias"]

function FieldHint({
  status,
  locked,
}: {
  status: FieldStatus
  locked?: boolean
}) {
  if (locked) {
    return null
  }

  if (!status.can_change && status.next_available_at) {
    return (
      <p className="text-xs text-muted-foreground">
        Available{" "}
        <FormattedDateTime
          value={status.next_available_at}
          display="contextual-relative"
          fallback="soon"
        />
      </p>
    )
  }

  return null
}

const settingsQueryKey = ["player-settings"]

const UserInformation = () => {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [aliasInput, setAliasInput] = useState("")
  const [customIdInput, setCustomIdInput] = useState("")
  const [countryInput, setCountryInput] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)

  const settingsQuery = useQuery({
    queryKey: settingsQueryKey,
    enabled: Boolean(currentUser),
    queryFn: () => PlayersService.readCurrentPlayerSettings(),
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
    setIsEditing(false)
  }, [player])

  const initialValues = useMemo(
    () => ({
      alias: player?.alias ?? "",
      customId: player?.custom_id ?? "",
      country: player?.country ?? null,
    }),
    [player],
  )

  const dirty =
    aliasInput !== initialValues.alias ||
    customIdInput !== initialValues.customId ||
    countryInput !== initialValues.country

  const mutation = useMutation({
    mutationFn: () => {
      const requestBody: {
        alias?: string
        custom_id?: string
        country?: string
      } = {}
      const alias = aliasInput.trim()
      const customId = customIdInput.trim()

      if (aliasInput !== initialValues.alias) {
        if (!alias) {
          throw new Error("Alias cannot be blank.")
        }
        requestBody.alias = alias
      }

      if (customIdInput !== initialValues.customId) {
        if (!customId) {
          throw new Error("Custom ID cannot be blank.")
        }
        requestBody.custom_id = customId
      }

      if (countryInput !== initialValues.country) {
        if (!countryInput) {
          throw new Error("Country cannot be cleared.")
        }
        requestBody.country = countryInput
      }

      return PlayersService.updateCurrentPlayerSettings({ requestBody })
    },
    onSuccess: (data) => {
      queryClient.setQueryData(settingsQueryKey, data)
      setIsEditing(false)
      showSuccessToast("Profile settings updated.")
    },
    onError: (error) => {
      showErrorToast(extractErrorMessage(error))
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: settingsQueryKey })
      void queryClient.invalidateQueries({ queryKey: ["currentUser"] })
      void queryClient.invalidateQueries({ queryKey: ["sidebar-user-player"] })
      void queryClient.invalidateQueries({ queryKey: ["profile-player"] })
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

  return (
    <Card className="max-w-2xl">
      <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <CardTitle>Profile</CardTitle>
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
                setIsEditing(false)
              }}
            >
              Cancel
            </Button>
            <LoadingButton
              type="submit"
              form="user-settings-form"
              loading={mutation.isPending}
              disabled={!dirty || settingsQuery.isLoading}
            >
              <Save className="size-4" />
              Save
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
            Edit
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
              <p className="text-sm text-muted-foreground">Steam name</p>
              <p className="font-medium">{player?.name ?? "Unknown"}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Steam ID64</p>
              <p className="font-mono text-sm">{currentUser.steamid64}</p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label htmlFor="settings-alias" className="text-sm font-medium">
                Alias
              </label>
              <Input
                id="settings-alias"
                value={aliasInput}
                maxLength={25}
                disabled={aliasDisabled}
                placeholder="Alias"
                onChange={(event) => setAliasInput(event.target.value)}
              />
              {settings ? <FieldHint status={settings.alias} /> : null}
            </div>

            <div className="space-y-2">
              <label
                htmlFor="settings-custom-id"
                className="text-sm font-medium"
              >
                Custom ID
              </label>
              <Input
                id="settings-custom-id"
                value={customIdInput}
                maxLength={25}
                disabled={customIdDisabled}
                placeholder="custom-id"
                onChange={(event) => setCustomIdInput(event.target.value)}
              />
              {settings ? <FieldHint status={settings.custom_id} /> : null}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <span className="text-sm font-medium">Country</span>
              <CountryPicker
                value={countryInput}
                onChange={setCountryInput}
                placeholder="Select a country"
                clearLabel="Clear country"
                disabled={countryDisabled}
              />
              {settings ? (
                <FieldHint
                  status={settings.country}
                  locked={settings.country_locked}
                />
              ) : null}
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

export default UserInformation
