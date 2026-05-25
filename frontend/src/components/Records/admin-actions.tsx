import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import { useState } from "react"

import type {
  RecordBulkDeleteCourse,
  RecordBulkDeleteResult,
  RecordPublic,
} from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
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
import useCustomToast from "@/hooks/useCustomToast"

type RecordDeleteTarget = Pick<RecordPublic, "map_name" | "stage"> & {
  player: Pick<RecordPublic["player"], "display_name" | "steamid64">
  map_id: number
}

function buildCourseDeleteLabel(record: RecordDeleteTarget) {
  return `${record.player.display_name} on ${record.map_name} ${record.stage === 0 ? "main" : `bonus ${record.stage}`}`
}

export function useRecordAdminActions() {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()

  const invalidateAll = () => {
    void queryClient.invalidateQueries({ queryKey: ["recent-records"] })
    void queryClient.invalidateQueries({ queryKey: ["profile-records"] })
    void queryClient.invalidateQueries({ queryKey: ["map-records"] })
    void queryClient.invalidateQueries({ queryKey: ["map", "leaderboard"] })
    void queryClient.invalidateQueries({ queryKey: ["map", "wrs"] })
    void queryClient.invalidateQueries({ queryKey: ["map", "stats"] })
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

  return {
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
            This will delete all records for {buildCourseDeleteLabel(record)}.
          </DialogDescription>
        </DialogHeader>
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
