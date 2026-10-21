import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import type {
  RecordBulkDeleteCourse,
  RecordBulkDeleteFaster,
  RecordBulkDeleteResult,
  RecordPublic,
} from "@/client"
import { RecordsService } from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import useCustomToast from "@/hooks/useCustomToast"
import { DeleteFasterRecordsPreview } from "./DeleteFasterRecordsPreview"
import { formatRecordTime } from "./utils"

type RecordDeleteTarget = Pick<RecordPublic, "map_name" | "stage"> & {
  player: Pick<RecordPublic["player"], "display_name" | "steamid64">
  map_id: number
}

function buildCourseDeleteLabel(record: RecordDeleteTarget) {
  return `${record.map_name} ${record.stage === 0 ? "main" : `bonus ${record.stage}`}`
}

export function useRecordAdminActions() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()

  const invalidateAll = () => {
    void queryClient.invalidateQueries({ queryKey: ["recent-records"] })
    void queryClient.invalidateQueries({ queryKey: ["profile-records"] })
    void queryClient.invalidateQueries({ queryKey: ["map-records"] })
    void queryClient.invalidateQueries({ queryKey: ["map", "leaderboard"] })
    void queryClient.invalidateQueries({ queryKey: ["me", "notifications"] })
  }

  const bulkDeleteMutation = useMutation({
    mutationFn: async (requestBody: RecordBulkDeleteCourse) => {
      const accessToken =
        typeof window === "undefined"
          ? null
          : window.localStorage.getItem("access_token")
      const response = await fetch(
        `${OpenAPI.BASE}/v1/records/bulk-delete-course`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
          body: JSON.stringify(requestBody),
        },
      )

      if (!response.ok) {
        const errorBody = await response.text()
        throw new Error(errorBody || "Bulk delete failed.")
      }

      return (await response.json()) as RecordBulkDeleteResult
    },
    onSuccess: (response) => {
      showSuccessToast(
        response.count === 1
          ? "Deleted 1 record."
          : `Deleted ${response.count} records.`,
      )
      invalidateAll()
    },
    onError: (error) => {
      showErrorToast(
        error instanceof Error ? error.message : "Bulk delete failed.",
      )
    },
  })

  const deleteFasterMutation = useMutation({
    mutationFn: (requestBody: RecordBulkDeleteFaster) =>
      RecordsService.bulkDeleteFasterRecords({ requestBody }),
    onSuccess: (response) => {
      showSuccessToast(t("recordModeration.deleted", { count: response.count }))
      invalidateAll()
    },
    onError: (error) => {
      if ((error as { status?: number }).status === 409) {
        showErrorToast(t("recordModeration.previewChanged"))
        void queryClient.invalidateQueries({
          queryKey: ["record-delete-faster-preview"],
        })
      } else {
        showErrorToast(t("recordModeration.failed"))
      }
    },
  })

  return {
    deleteFasterMutation,
    bulkDeleteMutation,
  }
}

export function DeleteCourseRecordsButton({
  bulkDeleteMutation,
  record,
}: {
  bulkDeleteMutation: ReturnType<
    typeof useRecordAdminActions
  >["bulkDeleteMutation"]
  record: RecordDeleteTarget
}) {
  const [open, setOpen] = useState(false)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
          disabled={bulkDeleteMutation.isPending}
          aria-label="Delete course records"
          title="Delete course records"
        >
          <Trash2 className="size-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Delete course records?</DialogTitle>
          <DialogDescription>
            This will delete all records on {buildCourseDeleteLabel(record)} for
            the following player.
          </DialogDescription>
        </DialogHeader>
        <PlayerDisplay player={record.player} showSteamid />
        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => setOpen(false)}
            disabled={bulkDeleteMutation.isPending}
          >
            Cancel
          </Button>
          <LoadingButton
            type="button"
            variant="destructive"
            loading={bulkDeleteMutation.isPending}
            onClick={async () => {
              await bulkDeleteMutation.mutateAsync({
                steamid64: record.player.steamid64,
                map_id: record.map_id,
                stage: record.stage,
              })
              setOpen(false)
            }}
          >
            Delete all
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export type DeleteFasterRecordsTarget = {
  record: RecordPublic
  scope: RecordBulkDeleteFaster["scope"]
  type: RecordBulkDeleteFaster["type"]
}

export function DeleteFasterRecordsDialog({
  target,
  onClose,
  mutation,
}: {
  target: DeleteFasterRecordsTarget | null
  onClose: () => void
  mutation: ReturnType<typeof useRecordAdminActions>["deleteFasterMutation"]
}) {
  const { t } = useTranslation()
  const preview = useQuery({
    queryKey: [
      "record-delete-faster-preview",
      target?.record.uuid,
      target?.scope,
      target?.type,
    ],
    queryFn: () =>
      RecordsService.previewBulkDeleteFasterRecords({
        requestBody: {
          record_uuid: target!.record.uuid,
          scope: target!.scope,
          type: target!.type,
        },
      }),
    enabled: target !== null,
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  })
  const canDelete =
    preview.isSuccess && !preview.isFetching && preview.data.count > 0
  return (
    <Dialog
      open={target !== null}
      onOpenChange={(open) => {
        if (!open && !mutation.isPending) onClose()
      }}
    >
      <DialogContent
        className="max-h-[90vh] overflow-y-auto sm:max-w-3xl"
        showCloseButton={!mutation.isPending}
      >
        <DialogHeader>
          <DialogTitle>{t("recordModeration.title")}</DialogTitle>
          <DialogDescription>
            {target
              ? t("recordModeration.description", {
                  map: target.record.map_name,
                  course:
                    target.record.stage === 0
                      ? t("maps.filters.mainStage")
                      : t("maps.filters.bonusStage", {
                          stage: target.record.stage,
                        }),
                  scope: target.scope,
                  type: target.type,
                  time: formatRecordTime(target.record.time),
                })
              : null}
          </DialogDescription>
        </DialogHeader>
        {preview.isFetching || preview.isPending ? (
          <output
            aria-label={t("recordModeration.previewLoading")}
            className="flex flex-col gap-2"
          >
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </output>
        ) : preview.isError ? (
          <Alert variant="destructive">
            <AlertDescription>
              <span>{t("recordModeration.previewFailed")}</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void preview.refetch()}
              >
                {t("recordModeration.previewRetry")}
              </Button>
            </AlertDescription>
          </Alert>
        ) : preview.data ? (
          <DeleteFasterRecordsPreview preview={preview.data} />
        ) : null}
        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            disabled={mutation.isPending}
            onClick={onClose}
          >
            {t("recordModeration.cancel")}
          </Button>
          <LoadingButton
            type="button"
            variant="destructive"
            loading={mutation.isPending}
            disabled={!canDelete}
            onClick={async () => {
              if (!target || mutation.isPending || !canDelete || !preview.data)
                return
              try {
                await mutation.mutateAsync({
                  record_uuid: target.record.uuid,
                  scope: target.scope,
                  type: target.type,
                  preview_token: preview.data.preview_token,
                })
                onClose()
              } catch {
                // The mutation shows an error toast; retain the confirmation for retry.
              }
            }}
          >
            {t("recordModeration.confirm")}
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
