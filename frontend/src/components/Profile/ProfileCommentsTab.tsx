import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import useAuth from "@/hooks/useAuth"
import { extractErrorMessage } from "@/utils"

import {
  createProfileComment,
  deleteProfileComment,
  getProfileCommentsQueryOptions,
  PROFILE_SOCIAL_PAGE_LIMIT,
  type ProfileComment,
} from "./profile-utils"

const MAX_COMMENT_LENGTH = 500

function CommentsSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-[420px] rounded-[28px]" />
      <Skeleton className="h-44 rounded-[28px]" />
    </div>
  )
}

function CommentRow({
  comment,
  canDelete,
  deleting,
  onDelete,
}: {
  comment: ProfileComment
  canDelete: boolean
  deleting: boolean
  onDelete: () => void
}) {
  return (
    <div
      className="space-y-4 py-1"
      data-testid={`profile-comment-row-${comment.id}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <PlayerDisplay
            player={{
              steamid64: comment.author.steamid64,
              display_name: comment.author.display_name,
            }}
            className="min-w-0"
          />
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <FormattedDateTime
            value={comment.created_at}
            display="contextual-relative"
            className="text-xs text-muted-foreground"
          />
          {canDelete ? (
            <Button
              type="button"
              variant="destructive"
              size="icon-sm"
              aria-label="Delete player comment"
              data-testid={`profile-comment-delete-${comment.id}`}
              disabled={deleting}
              onClick={onDelete}
            >
              <Trash2 className="size-4" />
            </Button>
          ) : null}
        </div>
      </div>
      <p className="whitespace-pre-wrap break-words pl-11 text-sm leading-6 text-foreground">
        {comment.text}
      </p>
    </div>
  )
}

export function ProfileCommentsTab({
  identifier,
  targetSteamid64,
}: {
  identifier: string
  targetSteamid64: string
}) {
  const { t } = useTranslation()
  const { loginWithSteam, user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const [text, setText] = useState("")
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(PROFILE_SOCIAL_PAGE_LIMIT)

  const offset = pageIndex * pageSize
  const commentsQuery = useQuery(
    getProfileCommentsQueryOptions({
      identifier,
      offset,
      limit: pageSize,
    }),
  )
  const viewerSteamid64 = currentUser?.steamid64 ?? null
  const canPost =
    viewerSteamid64 !== null && viewerSteamid64 !== targetSteamid64

  const comments = commentsQuery.data?.data ?? []
  const totalCount = commentsQuery.data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize))

  useEffect(() => {
    if (pageIndex < pageCount) {
      return
    }
    setPageIndex(Math.max(0, pageCount - 1))
  }, [pageCount, pageIndex])

  const invalidateComments = async () => {
    await queryClient.invalidateQueries({
      queryKey: ["profile-comments", identifier],
    })
  }

  const submitMutation = useMutation({
    mutationFn: async () => createProfileComment({ identifier, text }),
    onSuccess: async () => {
      setText("")
      setSubmitError(null)
      setPageIndex(0)
      await invalidateComments()
      toast.success(t("profile.comments.submitSuccess"))
    },
    onError: (error) => {
      setSubmitError(extractErrorMessage(error))
      toast.error(t("profile.comments.submitFailed"))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (commentId: string) =>
      deleteProfileComment({ identifier, commentId }),
    onSuccess: async () => {
      setDeleteError(null)
      await invalidateComments()
      toast.success(t("profile.comments.deleteSuccess"))
    },
    onError: (error) => {
      setDeleteError(extractErrorMessage(error))
      toast.error(t("profile.comments.deleteFailed"))
    },
  })

  const trimmedText = text.trim()
  const listError = useMemo(() => deleteError ?? null, [deleteError])

  if (commentsQuery.isLoading) {
    return <CommentsSkeleton />
  }

  if (commentsQuery.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t("profile.comments.loadFailedTitle")}</AlertTitle>
        <AlertDescription>
          {t("profile.comments.loadFailedBody")}
        </AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-4">
      <Card
        className="rounded-[28px] border border-border/70 bg-card/70"
        data-testid="profile-comments-card"
      >
        <CardContent className="p-0">
          {comments.length === 0 ? (
            <div
              className="px-6 py-10 text-sm text-muted-foreground sm:px-8"
              data-testid="profile-comments-empty"
            >
              {t("profile.comments.empty")}
            </div>
          ) : (
            <div
              className="px-6 py-6 sm:px-8"
              data-testid="profile-comments-list"
            >
              <div className="space-y-5">
                {comments.map((comment, index) => {
                  const canDelete =
                    viewerSteamid64 === comment.author.steamid64 ||
                    viewerSteamid64 === targetSteamid64
                  const isDeleting =
                    deleteMutation.isPending &&
                    deleteMutation.variables === comment.id

                  return (
                    <div key={comment.id}>
                      {index > 0 ? <Separator className="mb-5" /> : null}
                      <CommentRow
                        comment={comment}
                        canDelete={canDelete}
                        deleting={isDeleting}
                        onDelete={() => {
                          if (!canDelete || deleteMutation.isPending) {
                            return
                          }
                          if (
                            !window.confirm(t("profile.comments.deleteConfirm"))
                          ) {
                            return
                          }
                          setSubmitError(null)
                          void deleteMutation.mutateAsync(comment.id)
                        }}
                      />
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {listError ? (
            <div className="px-6 pb-6 sm:px-8">
              <Alert variant="destructive">
                <AlertTitle>
                  {t("profile.comments.deleteFailedTitle")}
                </AlertTitle>
                <AlertDescription>{listError}</AlertDescription>
              </Alert>
            </div>
          ) : null}

          {totalCount > 0 ? (
            <TablePaginationFooter
              totalLabel={t("profile.comments.totalLabel")}
              totalCount={totalCount}
              pageIndex={pageIndex}
              pageCount={pageCount}
              pageSize={pageSize}
              onPageIndexChange={setPageIndex}
              onPageSizeChange={(nextPageSize) => {
                setPageSize(nextPageSize)
                setPageIndex(0)
              }}
              pageSizeOptions={[10, 20, 50]}
            />
          ) : null}
        </CardContent>
      </Card>

      {viewerSteamid64 === null ? (
        <Alert data-testid="profile-comments-login">
          <AlertTitle>{t("profile.comments.loginTitle")}</AlertTitle>
          <AlertDescription className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>{t("profile.comments.loginBody")}</span>
            <Button type="button" size="sm" onClick={() => loginWithSteam()}>
              {t("auth.login")}
            </Button>
          </AlertDescription>
        </Alert>
      ) : canPost ? (
        <Card className="rounded-[28px] border border-border/70 bg-card/70">
          <CardContent className="space-y-4 p-6">
            <div className="space-y-2">
              <Label htmlFor="profile-comment-input">
                {t("profile.comments.formLabel")}
              </Label>
              <textarea
                id="profile-comment-input"
                rows={5}
                value={text}
                maxLength={MAX_COMMENT_LENGTH}
                placeholder={t("profile.comments.placeholder")}
                className="border-input focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive dark:bg-input/30 min-h-28 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px]"
                data-testid="profile-comments-form"
                onChange={(event) => {
                  setSubmitError(null)
                  setText(event.target.value)
                }}
              />
              <div className="flex justify-end text-xs text-muted-foreground">
                <span>
                  {text.length} / {MAX_COMMENT_LENGTH}
                </span>
              </div>
            </div>

            {submitError ? (
              <Alert variant="destructive">
                <AlertTitle>
                  {t("profile.comments.submitFailedTitle")}
                </AlertTitle>
                <AlertDescription>{submitError}</AlertDescription>
              </Alert>
            ) : null}

            <div className="flex justify-end">
              <Button
                type="button"
                disabled={submitMutation.isPending || trimmedText.length === 0}
                onClick={() => {
                  setDeleteError(null)
                  void submitMutation.mutateAsync()
                }}
              >
                {submitMutation.isPending
                  ? t("profile.comments.submitting")
                  : t("profile.comments.submit")}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
