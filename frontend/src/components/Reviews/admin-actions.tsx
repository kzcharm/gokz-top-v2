import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import { useState } from "react"

import { MapsService } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"

export type DeleteMapReviewCommentTarget = {
  mapId: number
  steamid64: string
  playerName: string
}

export function useMapReviewAdminActions() {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()

  const deleteCommentsMutation = useMutation({
    mutationFn: (target: DeleteMapReviewCommentTarget) =>
      MapsService.deleteMapReviewComments({
        mapId: target.mapId,
        steamid64: target.steamid64,
      }),
    onSuccess: async () => {
      showSuccessToast("Review comments deleted.")
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard", "reviews"] }),
        queryClient.invalidateQueries({ queryKey: ["map", "reviews"] }),
        queryClient.invalidateQueries({ queryKey: ["map"] }),
        queryClient.invalidateQueries({ queryKey: ["me", "notifications"] }),
        queryClient.invalidateQueries({
          queryKey: ["me", "notifications", "unread-count"],
        }),
      ])
    },
    onError: (error) => {
      showErrorToast(
        error instanceof Error
          ? error.message
          : "Failed to delete review comments.",
      )
    },
  })

  return { deleteCommentsMutation }
}

export function DeleteMapReviewCommentsButton({
  deleteCommentsMutation,
  target,
}: {
  deleteCommentsMutation: ReturnType<
    typeof useMapReviewAdminActions
  >["deleteCommentsMutation"]
  target: DeleteMapReviewCommentTarget
}) {
  const [confirmationOpen, setConfirmationOpen] = useState(false)
  const isPending =
    deleteCommentsMutation.isPending &&
    deleteCommentsMutation.variables?.mapId === target.mapId &&
    deleteCommentsMutation.variables?.steamid64 === target.steamid64

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="text-destructive hover:bg-destructive/10 hover:text-destructive"
        disabled={deleteCommentsMutation.isPending}
        aria-label={`Delete ${target.playerName}'s map review comments`}
        title="Delete review comments"
        onClick={() => setConfirmationOpen(true)}
      >
        <Trash2 className={isPending ? "size-4 animate-pulse" : "size-4"} />
      </Button>
      <Dialog open={confirmationOpen} onOpenChange={setConfirmationOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete review comments?</DialogTitle>
            <DialogDescription>
              Delete all map review comments by {target.playerName} on this map.
              Ratings will be kept.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmationOpen(false)}
              disabled={deleteCommentsMutation.isPending}
            >
              Cancel
            </Button>
            <LoadingButton
              type="button"
              variant="destructive"
              loading={isPending}
              disabled={deleteCommentsMutation.isPending && !isPending}
              onClick={() => {
                deleteCommentsMutation.mutate(target, {
                  onSuccess: () => setConfirmationOpen(false),
                })
              }}
            >
              Delete comments
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
