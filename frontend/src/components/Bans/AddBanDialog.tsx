import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { BansService, type BanType } from "@/client"
import { suppressRowInteractions } from "@/components/Common/interaction-suppression"
import type { PlayerDisplayPlayer } from "@/components/Common/PlayerDisplay"
import { PlayerSearchSelect } from "@/components/Common/PlayerSearchSelect"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
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

const BAN_TYPE_OPTIONS: Array<{ label: string; value: BanType }> = [
  { value: "ban_evasion", label: "Ban Evasion" },
  { value: "bhop_hack", label: "Bhop Hack" },
  { value: "bhop_macro", label: "Bhop Macro" },
  { value: "exploiting", label: "Exploiting" },
  { value: "strafe_hack", label: "Strafe Hack" },
  { value: "strafe_macro", label: "Strafe Macro" },
  { value: "other", label: "Other" },
]

const BAN_LENGTH_OPTIONS = [
  { value: "permanent", label: "Permanent" },
  { value: "1_week", label: "1 Week" },
  { value: "1_month", label: "1 Month" },
  { value: "3_months", label: "3 Months" },
  { value: "1_year", label: "1 Year" },
  { value: "3_years", label: "3 Years" },
] as const

type BanLengthValue = (typeof BAN_LENGTH_OPTIONS)[number]["value"]

type AddBanPlayer = PlayerDisplayPlayer & {
  steamid64: string
}

function getBanExpiryIso(length: BanLengthValue): string | null {
  if (length === "permanent") {
    return null
  }

  const expiresAt = new Date()
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

export function AddBanDialog({
  initialPlayer = null,
  open,
  onOpenChange,
}: {
  initialPlayer?: AddBanPlayer | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [selectedPlayer, setSelectedPlayer] = useState<AddBanPlayer | null>(
    null,
  )
  const [banType, setBanType] = useState<BanType | "">("")
  const [banLength, setBanLength] = useState<BanLengthValue>("permanent")
  const [notes, setNotes] = useState("")
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    setSelectedPlayer(initialPlayer)
    setBanType("")
    setBanLength("permanent")
    setNotes("")
    setFormError(null)
  }, [initialPlayer, open])

  useEffect(() => {
    if (!open) {
      return
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") {
        return
      }

      event.preventDefault()
      event.stopPropagation()
      onOpenChange(false)
    }

    window.addEventListener("keydown", handleEscape, true)
    return () => {
      window.removeEventListener("keydown", handleEscape, true)
    }
  }, [onOpenChange, open])

  const createBanMutation = useMutation({
    mutationFn: async () => {
      if (!selectedPlayer) {
        throw new Error("Choose a player before creating a ban.")
      }
      if (!banType) {
        throw new Error("Choose a ban type before creating a ban.")
      }

      return await BansService.createBan({
        requestBody: {
          steamid64: selectedPlayer.steamid64,
          ban_type: banType,
          expires_on: getBanExpiryIso(banLength),
          notes: notes.trim() || null,
        },
      })
    },
    onSuccess: (_data) => {
      showSuccessToast("Admin-created ban added.")
      onOpenChange(false)
    },
    onError: (error) => {
      const message = extractErrorMessage(error)
      setFormError(message)
      showErrorToast(message)
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["bans"] })
      if (selectedPlayer) {
        void queryClient.invalidateQueries({
          queryKey: ["profile-active-bans", selectedPlayer.steamid64],
        })
      }
    },
  })

  const pending = createBanMutation.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[calc(100vh-2rem)] overflow-y-auto sm:max-w-xl"
        onClick={(event) => event.stopPropagation()}
        onInteractOutside={(event) => {
          suppressRowInteractions()
          event.preventDefault()
        }}
        onEscapeKeyDown={() => onOpenChange(false)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            return
          }
          event.stopPropagation()
        }}
        onPointerDown={(event) => event.stopPropagation()}
        onPointerDownOutside={(event) => {
          suppressRowInteractions()
          event.preventDefault()
        }}
      >
        <DialogHeader>
          <DialogTitle>Add Ban</DialogTitle>
          <DialogDescription>
            Create an admin-only local ban. This action does not require a
            GlobalAPI id and does not change the upstream sync source.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <PlayerSearchSelect
            id="ban-player-search"
            ariaLabel="Player"
            label="Player"
            placeholder="Search player ..."
            required
            searchQueryKey="add-ban-dialog"
            selectedPlayer={selectedPlayer}
            onSelectPlayer={(player) => {
              setSelectedPlayer(player)
              setFormError(null)
            }}
            onClearPlayer={() => {
              setSelectedPlayer(null)
              setFormError(null)
            }}
          />

          <div className="grid gap-2">
            <label className="text-sm font-medium" htmlFor="ban-type">
              Ban Type
              <span aria-hidden="true" className="ml-1 text-destructive">
                *
              </span>
            </label>
            <Select
              value={banType}
              onValueChange={(value) => {
                setBanType(value as BanType)
                setFormError(null)
              }}
            >
              <SelectTrigger id="ban-type" className="w-full">
                <SelectValue placeholder="Choose a ban type" />
              </SelectTrigger>
              <SelectContent>
                {BAN_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <label className="text-sm font-medium" htmlFor="ban-length">
              Length
              <span aria-hidden="true" className="ml-1 text-destructive">
                *
              </span>
            </label>
            <Select
              value={banLength}
              onValueChange={(value) => setBanLength(value as BanLengthValue)}
            >
              <SelectTrigger id="ban-length" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BAN_LENGTH_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <label className="text-sm font-medium" htmlFor="ban-notes">
              Notes
            </label>
            <textarea
              id="ban-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={4}
              className="border-input focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive dark:bg-input/30 min-h-28 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px]"
              placeholder="Explain the admin-created ban."
            />
          </div>

          {formError ? (
            <div className="rounded-xl border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {formError}
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <button
            type="button"
            className="border-input hover:bg-accent hover:text-accent-foreground inline-flex items-center justify-center rounded-md border px-4 py-2 text-sm font-medium transition-colors"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            Cancel
          </button>
          <LoadingButton
            type="button"
            variant="destructive"
            loading={pending}
            onClick={() => {
              setFormError(null)
              void createBanMutation.mutateAsync()
            }}
          >
            Add Ban
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
