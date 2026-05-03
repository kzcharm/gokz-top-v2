import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, Pencil, Plus, Trash2 } from "lucide-react"
import { useState } from "react"

import { type PlayerSocialLinkPublic, PlayersService } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import {
  detectSocialPlatformFromUrl,
  getSocialPlatformLabel,
  SocialPlatformIcon,
  socialPlatformConfig,
} from "@/lib/social-links"
import { handleError } from "@/utils"

function SocialLinkRow({
  link,
  onEdit,
  onDelete,
  deleting,
}: {
  link: PlayerSocialLinkPublic
  onEdit: (link: PlayerSocialLinkPublic) => void
  onDelete: (link: PlayerSocialLinkPublic) => void
  deleting: boolean
}) {
  const platformLabel = getSocialPlatformLabel(link.platform)

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border/70 px-3 py-2">
      <a
        href={link.url}
        target="_blank"
        rel="noreferrer"
        className="flex min-w-0 items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full border border-border/70 bg-background">
          <SocialPlatformIcon platform={link.platform} className="size-4" />
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-medium">{platformLabel}</span>
          <span className="block truncate text-xs text-muted-foreground">
            {link.account_identifier}
          </span>
        </span>
        {link.verified ? (
          <CheckCircle2 className="size-4 shrink-0 text-green-600" />
        ) : (
          <span className="shrink-0 rounded-full border border-dashed border-muted-foreground/50 px-2 py-0.5 text-[11px] text-muted-foreground">
            Unverified
          </span>
        )}
      </a>
      <div className="flex shrink-0 items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => onEdit(link)}
          aria-label={`Edit ${platformLabel} link`}
        >
          <Pencil className="size-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          disabled={deleting}
          onClick={() => onDelete(link)}
          aria-label={`Delete ${platformLabel} link`}
        >
          <Trash2 className="size-4" />
        </Button>
      </div>
    </div>
  )
}

export default function SocialLinksSettings() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [urlInput, setUrlInput] = useState("")
  const [editingLink, setEditingLink] = useState<PlayerSocialLinkPublic | null>(
    null,
  )
  const identifier = String(currentUser?.steamid64 ?? "")
  const queryKey = ["player-social-links", identifier]

  const { data, isLoading } = useQuery({
    queryKey,
    enabled: identifier.length > 0,
    queryFn: () =>
      PlayersService.readPlayerSocialLinks({
        identifier,
      }),
  })

  const createMutation = useMutation({
    mutationFn: (url: string) =>
      PlayersService.createPlayerSocialLink({
        identifier,
        requestBody: { url },
      }),
    onSuccess: () => {
      setUrlInput("")
      showSuccessToast("Social link added")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ linkId, url }: { linkId: string; url: string }) =>
      PlayersService.updatePlayerSocialLink({
        identifier,
        linkId,
        requestBody: { url },
      }),
    onSuccess: () => {
      setEditingLink(null)
      setUrlInput("")
      showSuccessToast("Social link updated")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey })
      void queryClient.invalidateQueries({
        queryKey: ["profile-player"],
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (linkId: string) =>
      PlayersService.deletePlayerSocialLink({
        identifier,
        linkId,
      }),
    onSuccess: () => {
      showSuccessToast("Social link deleted")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey })
    },
  })

  if (!currentUser) {
    return null
  }

  const links = data?.data ?? []
  const detectedPlatform = detectSocialPlatformFromUrl(urlInput)
  const placeholder =
    detectedPlatform !== null
      ? socialPlatformConfig[detectedPlatform].placeholder
      : "https://x.com/username"
  const pending =
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending

  const submit = () => {
    const url = urlInput.trim()
    if (!url) {
      showErrorToast("Enter a social profile URL")
      return
    }

    if (editingLink) {
      updateMutation.mutate({ linkId: editingLink.id, url })
      return
    }

    createMutation.mutate(url)
  }

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h3 className="py-4 text-lg font-semibold">Social Links</h3>
      </div>
      <div className="space-y-3 rounded-lg border p-4">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="min-w-0 flex-1">
            <Input
              aria-label="Social profile URL"
              value={urlInput}
              placeholder={placeholder}
              onChange={(event) => setUrlInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault()
                  submit()
                }
              }}
            />
            {detectedPlatform ? (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
                <SocialPlatformIcon
                  platform={detectedPlatform}
                  className="size-3.5"
                />
                Detected {getSocialPlatformLabel(detectedPlatform)}
              </p>
            ) : null}
          </div>
          <LoadingButton loading={pending} type="button" onClick={submit}>
            {editingLink ? (
              <>
                <Pencil className="size-4" />
                Save
              </>
            ) : (
              <>
                <Plus className="size-4" />
                Add
              </>
            )}
          </LoadingButton>
          {editingLink ? (
            <Button
              type="button"
              variant="outline"
              disabled={pending}
              onClick={() => {
                setEditingLink(null)
                setUrlInput("")
              }}
            >
              Cancel
            </Button>
          ) : null}
        </div>

        <div className="space-y-2">
          {isLoading ? (
            <p className="py-4 text-sm text-muted-foreground">
              Loading social links...
            </p>
          ) : links.length > 0 ? (
            links.map((link) => (
              <SocialLinkRow
                key={link.id}
                link={link}
                deleting={deleteMutation.isPending}
                onEdit={(selectedLink) => {
                  setEditingLink(selectedLink)
                  setUrlInput(selectedLink.url)
                }}
                onDelete={(selectedLink) =>
                  deleteMutation.mutate(selectedLink.id)
                }
              />
            ))
          ) : (
            <p className="py-4 text-sm text-muted-foreground">
              No social links added yet.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
