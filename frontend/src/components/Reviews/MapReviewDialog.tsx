import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Star } from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import { type ApiError, type MapReviewPublic, MapsService } from "@/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { extractErrorMessage } from "@/utils"

const ratingValues = ["1", "2", "3", "4", "5"] as const

type MapReviewFormValues = {
  overall: (typeof ratingValues)[number]
  gameplay: "none" | (typeof ratingValues)[number]
  visuals: "none" | (typeof ratingValues)[number]
  comment: string
}

const DEFAULT_FORM_VALUES: MapReviewFormValues = {
  overall: "3",
  gameplay: "none",
  visuals: "none",
  comment: "",
}

function reviewToFormValues(
  review: MapReviewPublic | null,
): MapReviewFormValues {
  if (review === null) {
    return DEFAULT_FORM_VALUES
  }

  return {
    overall: String(review.content.overall) as MapReviewFormValues["overall"],
    gameplay:
      review.content.gameplay === null || review.content.gameplay === undefined
        ? "none"
        : (String(review.content.gameplay) as MapReviewFormValues["gameplay"]),
    visuals:
      review.content.visuals === null || review.content.visuals === undefined
        ? "none"
        : (String(review.content.visuals) as MapReviewFormValues["visuals"]),
    comment: review.content.comment?.text ?? "",
  }
}

function mapReviewFormToPayload(values: MapReviewFormValues, mapId: number) {
  const trimmedComment = values.comment.trim()

  return {
    map_id: mapId,
    content: {
      overall: Number(values.overall),
      gameplay: values.gameplay === "none" ? null : Number(values.gameplay),
      visuals: values.visuals === "none" ? null : Number(values.visuals),
      comment: trimmedComment.length > 0 ? { text: trimmedComment } : null,
    },
  }
}

function StarRatingRow({
  id,
  label,
  value,
  onChange,
  required = false,
}: {
  id: string
  label: string
  value: "none" | (typeof ratingValues)[number]
  onChange: (value: "none" | (typeof ratingValues)[number]) => void
  required?: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <div id={`${id}-label`} className="min-w-20 text-sm font-medium">
        {label}
        {required ? <span className="ml-1 text-destructive">*</span> : null}
      </div>
      <div
        role="radiogroup"
        aria-labelledby={`${id}-label`}
        className="flex flex-wrap items-center gap-1"
      >
        {ratingValues.map((ratingValue) => {
          const isActive =
            value !== "none" && Number(ratingValue) <= Number(value)
          const isCurrent = value === ratingValue

          return (
            <button
              key={ratingValue}
              type="button"
              aria-label={`${label} ${ratingValue} star${ratingValue === "1" ? "" : "s"}`}
              aria-pressed={isCurrent}
              data-testid={`${id}-star-${ratingValue}`}
              onClick={() => onChange(ratingValue)}
              className="inline-flex h-8 w-8 items-center justify-center text-muted-foreground transition hover:text-amber-500 focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              <Star
                className={`h-5 w-5 ${isActive ? "fill-amber-400 text-amber-400" : "text-muted-foreground/50"}`}
              />
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function MapReviewDialog({
  open,
  onOpenChange,
  mapId,
  mapName,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  mapId: number
  mapName: string
}) {
  const queryClient = useQueryClient()
  const { loginWithSteam, user: currentUser } = useAuth()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const authenticated = isLoggedIn()
  const viewerSteamid64 = currentUser?.steamid64 ?? null
  const [formValues, setFormValues] =
    useState<MapReviewFormValues>(DEFAULT_FORM_VALUES)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const latestReviewQuery = useQuery({
    queryKey: ["map", "review-dialog", "latest", mapId, viewerSteamid64],
    queryFn: () =>
      MapsService.readMapReviews({
        mapId,
        steamid64: viewerSteamid64 as unknown as number,
        limit: 1,
        source: "latest",
      }),
    enabled: open && viewerSteamid64 !== null,
    staleTime: 0,
  })

  const websiteReviewQuery = useQuery({
    queryKey: ["map", "review-dialog", "website", mapId, viewerSteamid64],
    queryFn: () =>
      MapsService.readMapReviews({
        mapId,
        steamid64: viewerSteamid64 as unknown as number,
        limit: 1,
        source: "website",
      }),
    enabled: open && viewerSteamid64 !== null,
    staleTime: 0,
  })

  const latestReview = latestReviewQuery.data?.data[0] ?? null
  const websiteReview = websiteReviewQuery.data?.data[0] ?? null
  const preferredReview = websiteReview ?? latestReview
  const hasAnyExistingReview = latestReview !== null
  const seededFromServerGroupReview =
    websiteReview === null && latestReview?.server_group_id !== null
  const reviewQueriesLoading =
    authenticated &&
    (currentUser === undefined ||
      (viewerSteamid64 !== null &&
        (latestReviewQuery.isLoading || websiteReviewQuery.isLoading)))
  const reviewQueriesError =
    latestReviewQuery.isError || websiteReviewQuery.isError
  const reviewQueryErrorMessage = latestReviewQuery.isError
    ? extractErrorMessage(latestReviewQuery.error)
    : websiteReviewQuery.isError
      ? extractErrorMessage(websiteReviewQuery.error)
      : null

  useEffect(() => {
    if (!open) {
      setFormValues(DEFAULT_FORM_VALUES)
      setSubmitError(null)
      setDeleteError(null)
      return
    }

    if (!authenticated) {
      setFormValues(DEFAULT_FORM_VALUES)
      return
    }

    if (
      viewerSteamid64 === null ||
      reviewQueriesLoading ||
      reviewQueriesError
    ) {
      return
    }

    setFormValues(reviewToFormValues(preferredReview))
    setSubmitError(null)
    setDeleteError(null)
  }, [
    authenticated,
    open,
    preferredReview,
    reviewQueriesError,
    reviewQueriesLoading,
    viewerSteamid64,
  ])

  const invalidateReviewQueries = async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["map", "review-dialog", "latest", mapId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["map", "review-dialog", "website", mapId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["map", "reviews", mapId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["map", mapName],
      }),
      queryClient.invalidateQueries({
        queryKey: ["maps", "catalog"],
      }),
      queryClient.invalidateQueries({
        queryKey: ["reviews"],
      }),
    ])
  }

  const submitMutation = useMutation({
    mutationFn: async (values: MapReviewFormValues) => {
      return await MapsService.putMapReview({
        requestBody: mapReviewFormToPayload(values, mapId),
      })
    },
    onSuccess: async (review) => {
      queryClient.setQueryData(
        ["map", "review-dialog", "website", mapId, viewerSteamid64],
        { data: [review], count: 1 },
      )
      queryClient.setQueryData(
        ["map", "review-dialog", "latest", mapId, viewerSteamid64],
        { data: [review], count: 1 },
      )
      await invalidateReviewQueries()
      showSuccessToast(
        websiteReview ? "Map review updated." : "Map review submitted.",
      )
      onOpenChange(false)
    },
    onError: (error: ApiError) => {
      const message = extractErrorMessage(error)
      setSubmitError(message)
      showErrorToast(message)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async () => {
      return await MapsService.deleteMapReviewComments({
        mapId,
      })
    },
    onSuccess: async (review) => {
      await invalidateReviewQueries()
      setFormValues(reviewToFormValues(review))
      setDeleteError(null)
      showSuccessToast("Review comments deleted.")
    },
    onError: (error: ApiError) => {
      const message = extractErrorMessage(error)
      setDeleteError(message)
      showErrorToast(message)
    },
  })

  const handleSubmit = () => {
    setSubmitError(null)
    setDeleteError(null)

    if (formValues.comment.length > 1000) {
      setSubmitError("Comment must be at most 1000 characters.")
      return
    }

    submitMutation.mutate(formValues)
  }

  const dialogDescription = useMemo(() => {
    if (!authenticated) {
      return `Log in with Steam to add or update your review for ${mapName}.`
    }
    return `Rate ${mapName}`
  }, [authenticated, mapName])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Add Review</DialogTitle>
          <DialogDescription>{dialogDescription}</DialogDescription>
        </DialogHeader>

        {!authenticated ? (
          <>
            <Alert>
              <AlertTitle>Login required</AlertTitle>
              <AlertDescription>
                You need to log in with Steam before submitting a map review.
              </AlertDescription>
            </Alert>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="button" onClick={loginWithSteam}>
                Continue with Steam
              </Button>
            </DialogFooter>
          </>
        ) : reviewQueriesLoading ? (
          <div className="space-y-3">
            <div className="h-10 animate-pulse rounded-md bg-muted" />
            <div className="h-10 animate-pulse rounded-md bg-muted" />
            <div className="h-28 animate-pulse rounded-md bg-muted" />
          </div>
        ) : reviewQueriesError ? (
          <Alert variant="destructive">
            <AlertTitle>Unable to load your review</AlertTitle>
            <AlertDescription>
              {reviewQueryErrorMessage ?? "Reload the page and try again."}
            </AlertDescription>
          </Alert>
        ) : (
          <div className="space-y-4">
            {seededFromServerGroupReview ? (
              <Alert>
                <AlertTitle>Server-group review detected</AlertTitle>
                <AlertDescription>
                  Deleting comments here clears comments from all of your
                  reviews on this map. Saving here only writes your website
                  review.
                </AlertDescription>
              </Alert>
            ) : null}

            <div className="grid gap-3">
              <StarRatingRow
                id="map-review-overall"
                label="Overall"
                value={formValues.overall}
                required
                onChange={(value) => {
                  setFormValues((current) => ({
                    ...current,
                    overall: value as MapReviewFormValues["overall"],
                  }))
                }}
              />

              <StarRatingRow
                id="map-review-gameplay"
                label="Gameplay"
                value={formValues.gameplay}
                onChange={(value) => {
                  setFormValues((current) => ({
                    ...current,
                    gameplay: value as MapReviewFormValues["gameplay"],
                  }))
                }}
              />

              <StarRatingRow
                id="map-review-visuals"
                label="Visuals"
                value={formValues.visuals}
                onChange={(value) => {
                  setFormValues((current) => ({
                    ...current,
                    visuals: value as MapReviewFormValues["visuals"],
                  }))
                }}
              />
            </div>

            <div className="grid gap-2">
              <label
                htmlFor="map-review-comment"
                className="text-sm font-medium"
              >
                Comment
              </label>
              <textarea
                id="map-review-comment"
                rows={5}
                value={formValues.comment}
                maxLength={1000}
                placeholder="Share what stood out about the map. Do not attack the author's family"
                onChange={(event) => {
                  setFormValues((current) => ({
                    ...current,
                    comment: event.target.value,
                  }))
                }}
                className="border-input focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive dark:bg-input/30 min-h-28 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px]"
              />
              <div className="flex justify-end text-xs text-muted-foreground">
                <span>{formValues.comment.length} / 1000</span>
              </div>
            </div>

            {submitError ? (
              <Alert variant="destructive">
                <AlertTitle>Unable to save review</AlertTitle>
                <AlertDescription>{submitError}</AlertDescription>
              </Alert>
            ) : null}

            {deleteError ? (
              <Alert variant="destructive">
                <AlertTitle>Unable to delete comments</AlertTitle>
                <AlertDescription>{deleteError}</AlertDescription>
              </Alert>
            ) : null}

            <DialogFooter className="gap-2 sm:justify-between">
              <div className="flex w-full flex-col-reverse gap-2 sm:w-auto sm:flex-row">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                  disabled={
                    submitMutation.isPending || deleteMutation.isPending
                  }
                >
                  Cancel
                </Button>
                {hasAnyExistingReview ? (
                  <LoadingButton
                    type="button"
                    variant="destructive"
                    loading={deleteMutation.isPending}
                    onClick={() => {
                      setSubmitError(null)
                      setDeleteError(null)
                      if (
                        !window.confirm(
                          "Delete all of your comments on this map? Ratings will be kept.",
                        )
                      ) {
                        return
                      }
                      deleteMutation.mutate()
                    }}
                    disabled={submitMutation.isPending}
                  >
                    Delete comments
                  </LoadingButton>
                ) : null}
              </div>
              <LoadingButton
                type="button"
                loading={submitMutation.isPending}
                disabled={deleteMutation.isPending}
                onClick={handleSubmit}
              >
                Save
              </LoadingButton>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
