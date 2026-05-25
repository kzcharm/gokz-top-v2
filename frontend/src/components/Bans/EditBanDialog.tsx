import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { BansService, type BanType } from "@/client"
import { suppressRowInteractions } from "@/components/Common/interaction-suppression"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useCustomToast from "@/hooks/useCustomToast"
import { extractErrorMessage } from "@/utils"
import {
  BAN_LENGTH_OPTIONS,
  type BanLengthValue,
  formatBanTypeLabel,
  getBanExpiryIsoFromDate,
  getBanLengthValueForExpiry,
  getUnbanExpiresAtIso,
  isoToLocalDateTimeInputValue,
  localDateTimeInputValueToIso,
} from "./ban-status"
import type { BanRow } from "./columns"

const BAN_TYPE_OPTIONS: BanType[] = [
  "ban_evasion",
  "bhop_hack",
  "bhop_macro",
  "exploiting",
  "strafe_hack",
  "strafe_macro",
  "other",
]

export function EditBanDialog({
  ban,
  open,
  onOpenChange,
}: {
  ban: BanRow | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [banType, setBanType] = useState<BanType>("other")
  const [notes, setNotes] = useState("")
  const [banLength, setBanLength] = useState<BanLengthValue | "custom">(
    "permanent",
  )
  const [expiresAtInputValue, setExpiresAtInputValue] = useState("")
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !ban) {
      return
    }

    setBanType(ban.ban_type as BanType)
    setNotes(ban.notes ?? "")
    setBanLength(
      getBanLengthValueForExpiry({
        createdAt: ban.created_at,
        expiresAt: ban.expires_at,
      }),
    )
    setExpiresAtInputValue(isoToLocalDateTimeInputValue(ban.expires_at))
    setFormError(null)
  }, [ban, open])

  const invalidateBans = () => {
    void queryClient.invalidateQueries({ queryKey: ["bans"] })
  }

  const updateBanMutation = useMutation({
    mutationFn: async ({
      expiresAt,
      nextBanType = banType,
      nextNotes = notes,
    }: {
      expiresAt: string | null
      nextBanType?: BanType
      nextNotes?: string
    }) => {
      if (!ban) {
        throw new Error("Choose a ban before editing.")
      }

      return await BansService.patchBan({
        banUuid: ban.uuid,
        requestBody: {
          ban_type: nextBanType,
          expires_at: expiresAt,
          notes: nextNotes.trim() || null,
        },
      })
    },
    onSuccess: () => {
      showSuccessToast("Ban updated.")
      onOpenChange(false)
    },
    onError: (error) => {
      const message = extractErrorMessage(error)
      setFormError(message)
      showErrorToast(message)
    },
    onSettled: () => {
      invalidateBans()
    },
  })

  const pending = updateBanMutation.isPending

  const submit = async () => {
    setFormError(null)
    if (banLength === "permanent") {
      await updateBanMutation.mutateAsync({ expiresAt: null })
      return
    }

    if (banLength === "custom") {
      const expiresAt = localDateTimeInputValueToIso(expiresAtInputValue)
      if (!expiresAt) {
        const message = "Choose a valid expiry date and time."
        setFormError(message)
        showErrorToast(message)
        return
      }

      await updateBanMutation.mutateAsync({ expiresAt })
      return
    }

    if (!ban) {
      return
    }

    const expiresAt = getBanExpiryIsoFromDate(ban.created_at, banLength)
    if (!expiresAt) {
      const message = "Unable to calculate expiry from the issued time."
      setFormError(message)
      showErrorToast(message)
      return
    }

    await updateBanMutation.mutateAsync({ expiresAt })
  }

  const unban = async () => {
    if (!ban) {
      return
    }

    setFormError(null)
    await updateBanMutation.mutateAsync({
      expiresAt: getUnbanExpiresAtIso(ban.created_at),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-xl"
        onClick={(event) => event.stopPropagation()}
        onInteractOutside={(event) => {
          suppressRowInteractions()
          event.preventDefault()
        }}
        onKeyDown={(event) => event.stopPropagation()}
        onPointerDown={(event) => event.stopPropagation()}
        onPointerDownOutside={(event) => {
          suppressRowInteractions()
          event.preventDefault()
        }}
      >
        <DialogHeader>
          <DialogTitle>Edit Ban</DialogTitle>
        </DialogHeader>

        {ban ? (
          <div className="grid gap-4">
            <div className="grid gap-2">
              <label className="text-sm font-medium" htmlFor="edit-ban-type">
                Ban Type
              </label>
              <Select
                value={banType}
                onValueChange={(value) => {
                  setBanType(value as BanType)
                  setFormError(null)
                }}
              >
                <SelectTrigger id="edit-ban-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BAN_TYPE_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {formatBanTypeLabel(option)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <label className="text-sm font-medium" htmlFor="edit-ban-length">
                Length
              </label>
              <Select
                value={banLength}
                onValueChange={(value) => {
                  setBanLength(value as BanLengthValue | "custom")
                  setFormError(null)
                }}
              >
                <SelectTrigger id="edit-ban-length" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BAN_LENGTH_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                  <SelectItem value="custom">Custom</SelectItem>
                </SelectContent>
              </Select>
              {banLength === "custom" ? (
                <div className="grid gap-2">
                  <label
                    className="text-sm font-medium"
                    htmlFor="edit-ban-expires-at"
                  >
                    Expires At
                  </label>
                  <Input
                    id="edit-ban-expires-at"
                    type="datetime-local"
                    value={expiresAtInputValue}
                    onChange={(event) => {
                      setExpiresAtInputValue(event.target.value)
                      setFormError(null)
                    }}
                  />
                </div>
              ) : null}
            </div>

            <div className="grid gap-2">
              <label className="text-sm font-medium" htmlFor="edit-ban-notes">
                Notes
              </label>
              <textarea
                id="edit-ban-notes"
                value={notes}
                onChange={(event) => {
                  setNotes(event.target.value)
                  setFormError(null)
                }}
                rows={4}
                className="border-input focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive dark:bg-input/30 min-h-28 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px]"
                placeholder="Explain the moderation change."
              />
            </div>

            {formError ? (
              <div className="rounded-xl border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                {formError}
              </div>
            ) : null}
          </div>
        ) : null}

        <DialogFooter className="flex-col-reverse gap-2 sm:flex-row sm:justify-between">
          <Button
            type="button"
            variant="ghost"
            className="sm:mr-auto text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={pending || ban === null}
            onClick={() => {
              void unban()
            }}
          >
            Unban
          </Button>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              disabled={pending}
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <LoadingButton
              type="button"
              loading={pending}
              onClick={() => {
                void submit()
              }}
            >
              Save
            </LoadingButton>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
