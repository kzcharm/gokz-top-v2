import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"

import { OpenAPI, type PlayerSocialLinkPublic, PlayersService } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import {
  detectSocialPlatformFromUrl,
  getSocialPlatformLabel,
  SocialPlatformIcon,
  socialPlatformConfig,
  socialPlatformOrder,
} from "@/lib/social-links"
import { extractErrorMessage, handleError } from "@/utils"

type TwitchMismatchState = {
  authenticatedAccount: string
  authenticatedDisplayName: string
  currentAccount: string
  linkId: string
  pendingToken: string
}

type SocialLinkDialogState =
  | { mode: "add" }
  | { mode: "edit"; link: PlayerSocialLinkPublic }

type TwitchVerificationMessage =
  | {
      type: "twitch-social-link-verification"
      status: "success"
    }
  | {
      type: "twitch-social-link-verification"
      status: "error"
      message: string
    }
  | {
      type: "twitch-social-link-verification"
      status: "mismatch"
      pendingToken: string
      linkId: string
      currentAccount: string
      authenticatedAccount: string
      authenticatedDisplayName: string
    }

function getAccessToken() {
  return localStorage.getItem("access_token") || ""
}

async function parseJsonResponse(response: Response) {
  try {
    return (await response.json()) as unknown
  } catch {
    return null
  }
}

async function throwResponseError(response: Response): Promise<never> {
  const body = await parseJsonResponse(response)
  const detail =
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string"
      ? body.detail
      : `${response.status} ${response.statusText}`.trim()
  throw new Error(detail || "Something went wrong.")
}

function openPopup(url: string) {
  const popup = window.open(url, "_blank")
  if (popup) {
    popup.focus()
  }
  return popup
}

async function startTwitchVerification(
  identifier: string,
  linkId: string,
): Promise<string> {
  const response = await fetch(
    `${OpenAPI.BASE}/v1/players/${encodeURIComponent(identifier)}/social-links/${linkId}/verify/twitch/start`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${getAccessToken()}`,
      },
      credentials: OpenAPI.CREDENTIALS,
    },
  )

  if (!response.ok) {
    await throwResponseError(response)
  }

  const payload = (await response.json()) as { authorization_url: string }
  return payload.authorization_url
}

async function startTwitchAdd(identifier: string): Promise<string> {
  const response = await fetch(
    `${OpenAPI.BASE}/v1/players/${encodeURIComponent(identifier)}/social-links/add/twitch/start`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${getAccessToken()}`,
      },
      credentials: OpenAPI.CREDENTIALS,
    },
  )

  if (!response.ok) {
    await throwResponseError(response)
  }

  const payload = (await response.json()) as { authorization_url: string }
  return payload.authorization_url
}

async function confirmTwitchVerification(
  identifier: string,
  linkId: string,
  pendingToken: string,
) {
  const response = await fetch(
    `${OpenAPI.BASE}/v1/players/${encodeURIComponent(identifier)}/social-links/${linkId}/verify/twitch/confirm`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getAccessToken()}`,
      },
      body: JSON.stringify({ pending_token: pendingToken }),
      credentials: OpenAPI.CREDENTIALS,
    },
  )

  if (!response.ok) {
    await throwResponseError(response)
  }

  return (await response.json()) as Awaited<
    ReturnType<typeof PlayersService.readPlayerSocialLinks>
  >
}

function SocialLinkRow({
  link,
  onEdit,
  onDelete,
  onVerify,
  deleting,
  verifying,
}: {
  link: PlayerSocialLinkPublic
  onEdit: (link: PlayerSocialLinkPublic) => void
  onDelete: (link: PlayerSocialLinkPublic) => void
  onVerify: (link: PlayerSocialLinkPublic) => void
  deleting: boolean
  verifying: boolean
}) {
  const platformLabel = getSocialPlatformLabel(link.platform)
  const isTwitchVerifyAvailable = link.platform === "twitch" && !link.verified

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
        {!link.verified ? (
          isTwitchVerifyAvailable ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={verifying}
              onClick={() => onVerify(link)}
            >
              <ShieldCheck className="size-4" />
              Verify
            </Button>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button type="button" variant="ghost" size="sm" disabled>
                    <ShieldCheck className="size-4" />
                    Verify
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent sideOffset={6}>
                Verification is not available for {platformLabel} yet.
              </TooltipContent>
            </Tooltip>
          )
        ) : null}
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
  const [dialogState, setDialogState] = useState<SocialLinkDialogState | null>(
    null,
  )
  const [draftUrl, setDraftUrl] = useState("")
  const [mismatchState, setMismatchState] =
    useState<TwitchMismatchState | null>(null)
  const identifier = String(currentUser?.steamid64 ?? "")
  const queryKey = useMemo(
    () => ["player-social-links", identifier],
    [identifier],
  )

  const { data, isLoading } = useQuery({
    queryKey,
    enabled: identifier.length > 0,
    queryFn: () =>
      PlayersService.readPlayerSocialLinks({
        identifier,
      }),
  })

  const links = data?.data ?? []
  const twitchLinked = links.some((link) => link.platform === "twitch")

  const refreshLinks = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey })
    void queryClient.invalidateQueries({
      queryKey: ["profile-player"],
    })
  }, [queryClient, queryKey])

  const handleTwitchVerificationResult = useCallback(
    (result: TwitchVerificationMessage) => {
      if (result.status === "success") {
        setMismatchState(null)
        setDialogState(null)
        showSuccessToast("Twitch account linked")
        refreshLinks()
        return
      }

      if (result.status === "error") {
        setMismatchState(null)
        showErrorToast(result.message)
        refreshLinks()
        return
      }

      setDialogState(null)
      setMismatchState({
        pendingToken: result.pendingToken,
        linkId: result.linkId,
        currentAccount: result.currentAccount,
        authenticatedAccount: result.authenticatedAccount,
        authenticatedDisplayName: result.authenticatedDisplayName,
      })
    },
    [refreshLinks, showErrorToast, showSuccessToast],
  )

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) {
        return
      }
      const data = event.data as Partial<TwitchVerificationMessage> | null
      if (
        !data ||
        data.type !== "twitch-social-link-verification" ||
        (data.status !== "success" &&
          data.status !== "error" &&
          data.status !== "mismatch")
      ) {
        return
      }
      handleTwitchVerificationResult(data as TwitchVerificationMessage)
    }

    window.addEventListener("message", onMessage)
    return () => window.removeEventListener("message", onMessage)
  }, [handleTwitchVerificationResult])

  useEffect(() => {
    const url = new URL(window.location.href)
    const status = url.searchParams.get("twitchVerification")
    if (!status) {
      return
    }

    if (window.opener && window.opener !== window) {
      if (status === "success") {
        window.opener.postMessage(
          {
            type: "twitch-social-link-verification",
            status: "success",
          } satisfies TwitchVerificationMessage,
          window.location.origin,
        )
      } else if (status === "error") {
        window.opener.postMessage(
          {
            type: "twitch-social-link-verification",
            status: "error",
            message:
              url.searchParams.get("message") || "Twitch verification failed",
          } satisfies TwitchVerificationMessage,
          window.location.origin,
        )
      } else if (status === "mismatch") {
        const pendingToken = url.searchParams.get("pendingToken")
        const linkId = url.searchParams.get("linkId")
        const currentAccount = url.searchParams.get("currentAccount")
        const authenticatedAccount = url.searchParams.get(
          "authenticatedAccount",
        )
        const authenticatedDisplayName =
          url.searchParams.get("authenticatedDisplayName") ||
          authenticatedAccount

        if (
          pendingToken &&
          linkId &&
          currentAccount &&
          authenticatedAccount &&
          authenticatedDisplayName
        ) {
          window.opener.postMessage(
            {
              type: "twitch-social-link-verification",
              status: "mismatch",
              pendingToken,
              linkId,
              currentAccount,
              authenticatedAccount,
              authenticatedDisplayName,
            } satisfies TwitchVerificationMessage,
            window.location.origin,
          )
        }
      }
      window.close()
      return
    }

    if (status === "success") {
      handleTwitchVerificationResult({
        type: "twitch-social-link-verification",
        status: "success",
      })
    } else if (status === "error") {
      handleTwitchVerificationResult({
        type: "twitch-social-link-verification",
        status: "error",
        message:
          url.searchParams.get("message") || "Twitch verification failed",
      })
    } else if (status === "mismatch") {
      const pendingToken = url.searchParams.get("pendingToken")
      const linkId = url.searchParams.get("linkId")
      const currentAccount = url.searchParams.get("currentAccount")
      const authenticatedAccount = url.searchParams.get("authenticatedAccount")
      const authenticatedDisplayName =
        url.searchParams.get("authenticatedDisplayName") || authenticatedAccount

      if (
        pendingToken &&
        linkId &&
        currentAccount &&
        authenticatedAccount &&
        authenticatedDisplayName
      ) {
        handleTwitchVerificationResult({
          type: "twitch-social-link-verification",
          status: "mismatch",
          pendingToken,
          linkId,
          currentAccount,
          authenticatedAccount,
          authenticatedDisplayName,
        })
      } else {
        showErrorToast("Twitch verification returned incomplete mismatch data")
      }
    }

    url.searchParams.delete("twitchVerification")
    url.searchParams.delete("twitchAction")
    url.searchParams.delete("message")
    url.searchParams.delete("pendingToken")
    url.searchParams.delete("linkId")
    url.searchParams.delete("currentAccount")
    url.searchParams.delete("authenticatedAccount")
    url.searchParams.delete("authenticatedDisplayName")
    window.history.replaceState({}, "", url)
  }, [handleTwitchVerificationResult, showErrorToast])

  const createMutation = useMutation({
    mutationFn: (url: string) =>
      PlayersService.createPlayerSocialLink({
        identifier,
        requestBody: { url },
      }),
    onSuccess: () => {
      setDialogState(null)
      setDraftUrl("")
      showSuccessToast("Social link added")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: refreshLinks,
  })

  const updateMutation = useMutation({
    mutationFn: ({ linkId, url }: { linkId: string; url: string }) =>
      PlayersService.updatePlayerSocialLink({
        identifier,
        linkId,
        requestBody: { url },
      }),
    onSuccess: () => {
      setDialogState(null)
      setDraftUrl("")
      showSuccessToast("Social link updated")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: refreshLinks,
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
    onSettled: refreshLinks,
  })

  const verifyMutation = useMutation({
    mutationFn: async (linkId: string) => {
      const authorizationUrl = await startTwitchVerification(identifier, linkId)
      const popup = openPopup(authorizationUrl)
      if (!popup) {
        throw new Error("Allow popups to continue Twitch verification")
      }
    },
    onError: (error) => {
      showErrorToast(extractErrorMessage(error))
    },
  })

  const addTwitchMutation = useMutation({
    mutationFn: async () => {
      const authorizationUrl = await startTwitchAdd(identifier)
      const popup = openPopup(authorizationUrl)
      if (!popup) {
        throw new Error("Allow popups to continue Twitch linking")
      }
    },
    onError: (error) => {
      showErrorToast(extractErrorMessage(error))
    },
    onSuccess: () => {
      setDialogState(null)
    },
  })

  const confirmVerificationMutation = useMutation({
    mutationFn: ({
      linkId,
      pendingToken,
    }: {
      linkId: string
      pendingToken: string
    }) => confirmTwitchVerification(identifier, linkId, pendingToken),
    onSuccess: () => {
      setMismatchState(null)
      showSuccessToast("Twitch account linked")
    },
    onError: (error) => {
      showErrorToast(extractErrorMessage(error))
    },
    onSettled: refreshLinks,
  })

  if (!currentUser) {
    return null
  }

  const detectedPlatform = detectSocialPlatformFromUrl(draftUrl)
  const placeholder =
    detectedPlatform !== null
      ? socialPlatformConfig[detectedPlatform].placeholder
      : "https://x.com/username"
  const pending =
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending ||
    verifyMutation.isPending ||
    addTwitchMutation.isPending ||
    confirmVerificationMutation.isPending

  const submitDialog = () => {
    const url = draftUrl.trim()
    if (!url) {
      showErrorToast("Enter a social profile URL")
      return
    }

    if (!dialogState || dialogState.mode === "add") {
      createMutation.mutate(url)
      return
    }

    updateMutation.mutate({ linkId: dialogState.link.id, url })
  }

  const launchTwitchLogin = () => {
    if (dialogState?.mode === "add") {
      addTwitchMutation.mutate()
    } else if (dialogState?.mode === "edit") {
      verifyMutation.mutate(dialogState.link.id)
    }
  }

  return (
    <>
      <Card className="max-w-2xl">
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <CardTitle>Social Links</CardTitle>
          <Button
            type="button"
            onClick={() => {
              setDialogState({ mode: "add" })
              setDraftUrl("")
            }}
          >
            <Plus className="size-4" />
            Add
          </Button>
        </CardHeader>
        <CardContent className="space-y-2">
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
                verifying={verifyMutation.isPending}
                onEdit={(selectedLink) => {
                  setDialogState({ mode: "edit", link: selectedLink })
                  setDraftUrl(selectedLink.url)
                }}
                onDelete={(selectedLink) =>
                  deleteMutation.mutate(selectedLink.id)
                }
                onVerify={(selectedLink) =>
                  verifyMutation.mutate(selectedLink.id)
                }
              />
            ))
          ) : (
            <p className="py-4 text-sm text-muted-foreground">
              No social links added yet.
            </p>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={dialogState !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDialogState(null)
            setDraftUrl("")
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {dialogState?.mode === "edit"
                ? "Edit Social Link"
                : "Add Social Link"}
            </DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <label className="text-sm font-medium" htmlFor="social-url">
                URL
              </label>
              <Input
                id="social-url"
                aria-label="Social profile URL"
                value={draftUrl}
                placeholder={placeholder}
                onChange={(event) => setDraftUrl(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    submitDialog()
                  }
                }}
              />
              {detectedPlatform ? (
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <SocialPlatformIcon
                    platform={detectedPlatform}
                    className="size-3.5"
                  />
                  Detected {getSocialPlatformLabel(detectedPlatform)}
                </p>
              ) : null}
            </div>

            {dialogState?.mode === "add" ? (
              <div className="grid gap-2">
                <p className="text-sm font-medium">Quick link</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {socialPlatformOrder.map((platform) => {
                    const isTwitch = platform === "twitch"
                    const disabled = !isTwitch || twitchLinked
                    const label = isTwitch
                      ? twitchLinked
                        ? "Twitch already linked"
                        : "Link with Twitch"
                      : `${getSocialPlatformLabel(platform)} coming soon`

                    return (
                      <Tooltip key={platform}>
                        <TooltipTrigger asChild>
                          <span>
                            <Button
                              type="button"
                              variant="outline"
                              className="w-full justify-start"
                              disabled={disabled}
                              onClick={() => {
                                if (isTwitch && !twitchLinked) {
                                  launchTwitchLogin()
                                }
                              }}
                            >
                              <SocialPlatformIcon
                                platform={platform}
                                className="size-4"
                              />
                              {getSocialPlatformLabel(platform)}
                            </Button>
                          </span>
                        </TooltipTrigger>
                        <TooltipContent sideOffset={6}>{label}</TooltipContent>
                      </Tooltip>
                    )
                  })}
                </div>
              </div>
            ) : null}
          </div>
          <DialogFooter>
            {dialogState?.mode === "edit" ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => {
                    setDialogState(null)
                    setDraftUrl("")
                  }}
                >
                  Cancel
                </Button>
                <LoadingButton
                  loading={pending}
                  type="button"
                  onClick={submitDialog}
                >
                  Save
                </LoadingButton>
              </>
            ) : (
              <>
                <Button
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => {
                    setDialogState(null)
                    setDraftUrl("")
                  }}
                >
                  Cancel
                </Button>
                <LoadingButton
                  loading={pending}
                  type="button"
                  onClick={submitDialog}
                >
                  <Plus className="size-4" />
                  Add link
                </LoadingButton>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={mismatchState !== null}
        onOpenChange={(open) => {
          if (!open) {
            setMismatchState(null)
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm Twitch account</DialogTitle>
          </DialogHeader>
          {mismatchState ? (
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>
                You logged into Twitch as{" "}
                <span className="font-medium text-foreground">
                  {mismatchState.authenticatedDisplayName}
                </span>{" "}
                (
                <span className="font-mono text-foreground">
                  {mismatchState.authenticatedAccount}
                </span>
                ).
              </p>
              <p>
                Replace the current linked account{" "}
                <span className="font-mono text-foreground">
                  {mismatchState.currentAccount}
                </span>{" "}
                and mark it verified?
              </p>
            </div>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={confirmVerificationMutation.isPending}
              onClick={() => setMismatchState(null)}
            >
              Cancel
            </Button>
            <LoadingButton
              loading={confirmVerificationMutation.isPending}
              type="button"
              onClick={() => {
                if (!mismatchState) {
                  return
                }
                confirmVerificationMutation.mutate({
                  linkId: mismatchState.linkId,
                  pendingToken: mismatchState.pendingToken,
                })
              }}
            >
              Replace and verify
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
