import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { PlayerReportsService } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { suppressRowInteractions } from "@/components/Common/interaction-suppression"
import {
  PlayerDisplay,
  type PlayerDisplayPlayer,
} from "@/components/Common/PlayerDisplay"
import { formatRecordTime } from "@/components/Records/utils"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { extractErrorMessage } from "@/utils"

const MAX_REPORT_DESCRIPTION_LENGTH = 1000

export type ReportPlayerTarget = {
  steamid64: string
  displayName: string
  player?: PlayerDisplayPlayer | null
}

export type ReportRecordContext = {
  uuid: string
  mapName?: string | null
  mode?: string | null
  type?: string | null
  time?: number | null
  createdOn?: string | null
}

export function ReportPlayerDialog({
  open,
  onOpenChange,
  recordContext = null,
  target,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  recordContext?: ReportRecordContext | null
  target: ReportPlayerTarget
}) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [description, setDescription] = useState("")
  const [confirmationOpen, setConfirmationOpen] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    setDescription("")
    setConfirmationOpen(false)
    setFormError(null)
  }, [open])

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

  const createReportMutation = useMutation({
    mutationFn: async () => {
      const normalizedDescription = description.trim()

      return await PlayerReportsService.createPlayerReport({
        requestBody: {
          target_steamid64: target.steamid64,
          description: normalizedDescription || null,
          record_uuid: recordContext?.uuid ?? null,
        },
      })
    },
    onSuccess: () => {
      showSuccessToast("Report submitted.")
      setConfirmationOpen(false)
      onOpenChange(false)
    },
    onError: (error) => {
      const message = extractErrorMessage(error)
      setFormError(message)
      showErrorToast(message)
    },
    onSettled: () => {
      void queryClient.invalidateQueries({
        queryKey: ["me", "notifications", "unread-count"],
      })
    },
  })

  const pending = createReportMutation.isPending
  const normalizedDescriptionLength = description.trim().length
  const recordParts = recordContext
    ? [
        recordContext.mapName ?? "Unknown map",
        [recordContext.mode, recordContext.type]
          .filter((part): part is string => Boolean(part))
          .join(" ") || null,
        typeof recordContext.time === "number"
          ? formatRecordTime(recordContext.time)
          : null,
      ].filter((part): part is string => Boolean(part))
    : []

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            setConfirmationOpen(false)
          }
          onOpenChange(nextOpen)
        }}
      >
        <DialogContent
          className="max-h-[calc(100vh-2rem)] overflow-y-auto sm:max-w-lg"
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
            <DialogTitle>Report Player</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4">
            <div className="grid gap-2 rounded-lg border border-border/70 bg-muted/20 p-3 text-sm">
              <PlayerDisplay
                player={
                  target.player ?? {
                    steamid64: target.steamid64,
                    name: target.displayName,
                  }
                }
                className="min-w-0 text-foreground"
                hideAvatarWithoutSteamid64
                showSteamid
              />
              {recordContext ? (
                <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                  <p>Record: {recordParts.join(" - ")}</p>
                  {recordContext.createdOn ? (
                    <p>
                      Submitted{" "}
                      <FormattedDateTime
                        value={recordContext.createdOn}
                        display="relative"
                      />
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              Reports are for serious issues only. Do not use this to tease your
              friends. Abuse of reports can result in a ban.
            </div>

            <div className="grid gap-2">
              <div className="flex items-center justify-between gap-3">
                <label
                  className="text-sm font-medium"
                  htmlFor="report-description"
                >
                  Description
                  <span className="ml-1 font-normal text-muted-foreground">
                    optional
                  </span>
                </label>
                <span className="text-xs text-muted-foreground">
                  {normalizedDescriptionLength} /{" "}
                  {MAX_REPORT_DESCRIPTION_LENGTH}
                </span>
              </div>
              <textarea
                id="report-description"
                value={description}
                maxLength={MAX_REPORT_DESCRIPTION_LENGTH}
                onChange={(event) => {
                  setDescription(event.target.value)
                  setFormError(null)
                }}
                rows={5}
                className="border-input focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive dark:bg-input/30 min-h-32 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px]"
                placeholder="Describe what happened and include any useful context."
              />
            </div>

            {formError ? (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
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
              loading={false}
              disabled={pending}
              onClick={() => {
                setFormError(null)
                setConfirmationOpen(true)
              }}
            >
              Submit Report
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={confirmationOpen} onOpenChange={setConfirmationOpen}>
        <DialogContent
          className="sm:max-w-md"
          onClick={(event) => event.stopPropagation()}
          onInteractOutside={(event) => {
            suppressRowInteractions()
            event.preventDefault()
          }}
          onPointerDown={(event) => event.stopPropagation()}
          onPointerDownOutside={(event) => {
            suppressRowInteractions()
            event.preventDefault()
          }}
        >
          <DialogHeader>
            <DialogTitle>Submit report?</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p>
              Send this report to admins for review. Do not submit reports as a
              joke or to tease friends.
            </p>
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-destructive">
              Abuse of reports can result in a ban.
            </div>
          </div>
          <DialogFooter>
            <button
              type="button"
              className="border-input hover:bg-accent hover:text-accent-foreground inline-flex items-center justify-center rounded-md border px-4 py-2 text-sm font-medium transition-colors"
              onClick={() => setConfirmationOpen(false)}
              disabled={pending}
            >
              Back
            </button>
            <LoadingButton
              type="button"
              loading={pending}
              variant="destructive"
              onClick={() => {
                setFormError(null)
                void createReportMutation.mutateAsync()
              }}
            >
              Confirm Report
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
