import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pencil, Plus, Send, Trash2 } from "lucide-react"
import { useState } from "react"
import { FaDiscord } from "react-icons/fa"

import { PlayersService, type PlayerWebhookPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { Switch } from "@/components/ui/switch"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { extractErrorMessage, handleError } from "@/utils"

const webhooksQueryKey = ["player-webhooks"]

function summarizeWebhookUrl(url: string) {
  const token = url.split("/").pop() ?? ""
  const tokenPreview = token.slice(0, 4) || "unknown"
  return `Discord webhook • ${tokenPreview}...`
}

function WebhookRow({
  webhook,
  busy,
  onToggle,
  onEdit,
  onDelete,
}: {
  webhook: PlayerWebhookPublic
  busy: boolean
  onToggle: (webhook: PlayerWebhookPublic, enabled: boolean) => void
  onEdit: (webhook: PlayerWebhookPublic) => void
  onDelete: (webhook: PlayerWebhookPublic) => void
}) {
  return (
    <div className="space-y-3 rounded-lg border border-border/70 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-2">
            <span className="inline-flex size-8 items-center justify-center rounded-full border border-border/70 bg-background">
              <FaDiscord className="size-4" />
            </span>
            <div>
              <p className="text-sm font-medium">Discord webhook</p>
            </div>
          </div>
          <p className="font-mono text-xs text-muted-foreground">
            {summarizeWebhookUrl(webhook.url)}
          </p>
          <p className="text-xs text-muted-foreground">
            Last tested:{" "}
            {webhook.last_tested_at ? (
              <FormattedDateTime
                value={webhook.last_tested_at}
                display="contextual-relative"
              />
            ) : (
              "Never"
            )}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Switch
              checked={webhook.enabled}
              disabled={busy}
              aria-label={`Toggle webhook ${webhook.id}`}
              onCheckedChange={(enabled) => onToggle(webhook, enabled)}
            />
            <span className="text-sm text-muted-foreground">
              {webhook.enabled ? "Enabled" : "Disabled"}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={busy}
              onClick={() => onEdit(webhook)}
              aria-label="Edit Discord webhook"
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="text-destructive hover:text-destructive"
              disabled={busy}
              onClick={() => onDelete(webhook)}
              aria-label="Delete Discord webhook"
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function WebhooksSettings() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
  const [newWebhookUrl, setNewWebhookUrl] = useState("")
  const [newWebhook, setNewWebhook] = useState<PlayerWebhookPublic | null>(null)
  const [editingUrl, setEditingUrl] = useState("")
  const [editingWebhook, setEditingWebhook] =
    useState<PlayerWebhookPublic | null>(null)

  const query = useQuery({
    queryKey: webhooksQueryKey,
    enabled: Boolean(currentUser),
    queryFn: () => PlayersService.readCurrentPlayerWebhooks(),
  })

  const createMutation = useMutation({
    mutationFn: (url: string) =>
      PlayersService.createCurrentPlayerWebhook({
        requestBody: { url },
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(webhooksQueryKey, data)
      const createdWebhook = data.data.find(
        (webhook) => webhook.url === newWebhookUrl.trim(),
      )
      setNewWebhook(createdWebhook ?? null)
      showSuccessToast("Webhook added")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: webhooksQueryKey })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({
      webhookId,
      requestBody,
    }: {
      webhookId: string
      requestBody: { url?: string; enabled?: boolean }
    }) =>
      PlayersService.updateCurrentPlayerWebhook({
        webhookId,
        requestBody,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(webhooksQueryKey, data)
      setEditingWebhook(null)
      setEditingUrl("")
      showSuccessToast("Webhook updated")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: webhooksQueryKey })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (webhookId: string) =>
      PlayersService.deleteCurrentPlayerWebhook({ webhookId }),
    onSuccess: (data) => {
      queryClient.setQueryData(webhooksQueryKey, data)
      showSuccessToast("Webhook deleted")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: webhooksQueryKey })
    },
  })

  const testMutation = useMutation({
    mutationFn: (webhookId: string) =>
      PlayersService.testCurrentPlayerWebhook({ webhookId }),
    onSuccess: (data) => {
      queryClient.setQueryData(
        webhooksQueryKey,
        (
          current: { data: PlayerWebhookPublic[]; count: number } | undefined,
        ) => {
          if (!current) {
            return current
          }
          return {
            ...current,
            data: current.data.map((webhook) =>
              webhook.id === data.id ? data : webhook,
            ),
          }
        },
      )
      setNewWebhook((current) => (current?.id === data.id ? data : current))
      showSuccessToast("Webhook test sent")
    },
    onError: (error) => {
      showErrorToast(extractErrorMessage(error))
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: webhooksQueryKey })
    },
  })

  if (!currentUser) {
    return null
  }

  const webhooks = query.data?.data ?? []
  const urlPlaceholder =
    "https://discord.com/api/webhooks/123456789012345678/your-webhook-token"

  const resetAddDialog = () => {
    setIsAddDialogOpen(false)
    setNewWebhookUrl("")
    setNewWebhook(null)
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="space-y-2 rounded-lg border p-4">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-lg font-semibold">Discord webhooks</h3>
          <Button
            type="button"
            variant="outline"
            disabled={query.isLoading}
            onClick={() => setIsAddDialogOpen(true)}
          >
            <Plus className="size-4" /> Add
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Receive pretty Discord embed notifications when your verified Twitch
          or Bilibili stream starts.
        </p>
      </div>

      <div className="space-y-3">
        {webhooks.length > 0 ? (
          webhooks.map((webhook) => {
            const busy =
              updateMutation.isPending ||
              deleteMutation.isPending ||
              createMutation.isPending

            return (
              <WebhookRow
                key={webhook.id}
                webhook={webhook}
                busy={busy}
                onToggle={(currentWebhook, enabled) =>
                  updateMutation.mutate({
                    webhookId: currentWebhook.id,
                    requestBody: { enabled },
                  })
                }
                onEdit={(currentWebhook) => {
                  setEditingWebhook(currentWebhook)
                  setEditingUrl(currentWebhook.url)
                }}
                onDelete={(currentWebhook) =>
                  deleteMutation.mutate(currentWebhook.id)
                }
              />
            )
          })
        ) : (
          <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
            No webhooks added yet.
          </div>
        )}
      </div>

      <Dialog
        open={isAddDialogOpen}
        onOpenChange={(open) => {
          if (!open) {
            resetAddDialog()
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Discord webhook</DialogTitle>
          </DialogHeader>
          <form
            id="add-webhook-form"
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              const url = newWebhookUrl.trim()
              if (!url) {
                showErrorToast("Webhook URL cannot be blank.")
                return
              }
              createMutation.mutate(url)
            }}
          >
            <Input
              value={newWebhookUrl}
              placeholder={urlPlaceholder}
              aria-label="Discord webhook URL"
              disabled={createMutation.isPending}
              onChange={(event) => setNewWebhookUrl(event.target.value)}
            />
            {newWebhook ? (
              <p className="text-xs text-muted-foreground">
                Webhook created. Use Send test to preview the Discord embed.
              </p>
            ) : null}
          </form>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={createMutation.isPending || testMutation.isPending}
              onClick={resetAddDialog}
            >
              Close
            </Button>
            {newWebhook ? (
              <LoadingButton
                type="button"
                loading={
                  testMutation.isPending &&
                  testMutation.variables === newWebhook.id
                }
                onClick={() => testMutation.mutate(newWebhook.id)}
              >
                <Send className="size-4" />
                Send test
              </LoadingButton>
            ) : null}
            <LoadingButton
              type="submit"
              form="add-webhook-form"
              loading={createMutation.isPending}
              disabled={query.isLoading || newWebhook !== null}
            >
              Save
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={editingWebhook !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditingWebhook(null)
            setEditingUrl("")
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Discord webhook</DialogTitle>
          </DialogHeader>
          <form
            id="edit-webhook-form"
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              if (!editingWebhook) {
                return
              }
              const url = editingUrl.trim()
              if (!url) {
                showErrorToast("Webhook URL cannot be blank.")
                return
              }
              updateMutation.mutate({
                webhookId: editingWebhook.id,
                requestBody: { url },
              })
            }}
          >
            <Input
              value={editingUrl}
              placeholder={urlPlaceholder}
              aria-label="Edit Discord webhook URL"
              disabled={updateMutation.isPending}
              onChange={(event) => setEditingUrl(event.target.value)}
            />
          </form>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={updateMutation.isPending}
              onClick={() => {
                setEditingWebhook(null)
                setEditingUrl("")
              }}
            >
              Cancel
            </Button>
            <LoadingButton
              type="submit"
              form="edit-webhook-form"
              loading={updateMutation.isPending}
            >
              Save
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
