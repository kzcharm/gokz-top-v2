import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { PlayerReportsService } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { suppressRowInteractions } from "@/components/Common/interaction-suppression"
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
}

export type ReportRecordContext = {
  uuid: string
  mapName?: string | null
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
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    setDescription("")
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
      if (!normalizedDescription) {
        throw new Error("Add a description before submitting the report.")
      }

      return await PlayerReportsService.createPlayerReport({
        requestBody: {
          target_steamid64: target.steamid64,
          description: normalizedDescription,
          record_uuid: recordContext?.uuid ?? null,
        },
      })
    },
    onSuccess: () => {
      showSuccessToast("Report submitted.")
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
          <div className="grid gap-1 rounded-lg border border-border/70 bg-muted/20 p-3 text-sm">
            <p className="font-medium">{target.displayName}</p>
            <p className="font-mono text-xs text-muted-foreground">
              {target.steamid64}
            </p>
            {recordContext ? (
              <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                <p>
                  Record context: {recordContext.mapName ?? "Unknown map"}
                  {typeof recordContext.time === "number"
                    ? ` - ${formatRecordTime(recordContext.time)}`
                    : ""}
                </p>
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
                <span aria-hidden="true" className="ml-1 text-destructive">
                  *
                </span>
              </label>
              <span className="text-xs text-muted-foreground">
                {normalizedDescriptionLength} / {MAX_REPORT_DESCRIPTION_LENGTH}
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
            loading={pending}
            disabled={normalizedDescriptionLength === 0}
            onClick={() => {
              setFormError(null)
              void createReportMutation.mutateAsync()
            }}
          >
            Submit Report
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
