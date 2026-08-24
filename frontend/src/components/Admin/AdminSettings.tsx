import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Copy, Eye, RotateCw, ShieldCheck, Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { AdminSettingsService } from "@/client"
import {
  AdminControlsCard,
  AdminPageHeader,
} from "@/components/Admin/AdminPageLayout"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import useCustomToast from "@/hooks/useCustomToast"
import { extractErrorMessage } from "@/utils"

type ConfirmationAction = "rotate" | "revoke" | null

const secretStatusQueryKey = ["admin-settings", "qq-binding-secret"] as const

export default function AdminSettings() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [_copiedValue, copyToClipboard] = useCopyToClipboard()
  const [secret, setSecret] = useState<string | null>(null)
  const [confirmationAction, setConfirmationAction] =
    useState<ConfirmationAction>(null)
  const statusQuery = useQuery({
    queryKey: secretStatusQueryKey,
    queryFn: AdminSettingsService.readAdminQqBindingSecretStatus,
  })

  const refreshStatus = () =>
    queryClient.invalidateQueries({ queryKey: secretStatusQueryKey })

  const generateMutation = useMutation({
    mutationFn: AdminSettingsService.generateAdminQqBindingSecret,
    onSuccess: (data) => {
      setSecret(data.secret)
      void refreshStatus()
      showSuccessToast(t("adminSettings.qqBinding.toasts.generated"))
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })
  const revealMutation = useMutation({
    mutationFn: AdminSettingsService.revealAdminQqBindingSecret,
    onSuccess: (data) => setSecret(data.secret),
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })
  const rotateMutation = useMutation({
    mutationFn: AdminSettingsService.rotateAdminQqBindingSecret,
    onSuccess: (data) => {
      setSecret(data.secret)
      setConfirmationAction(null)
      void refreshStatus()
      showSuccessToast(t("adminSettings.qqBinding.toasts.rotated"))
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })
  const revokeMutation = useMutation({
    mutationFn: AdminSettingsService.revokeAdminQqBindingSecret,
    onSuccess: () => {
      setSecret(null)
      setConfirmationAction(null)
      void refreshStatus()
      showSuccessToast(t("adminSettings.qqBinding.toasts.revoked"))
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

  const configured = statusQuery.data?.configured === true
  const pending =
    generateMutation.isPending ||
    revealMutation.isPending ||
    rotateMutation.isPending ||
    revokeMutation.isPending

  const copySecret = async () => {
    if (secret === null) return
    if (!(await copyToClipboard(secret))) {
      showErrorToast(
        t("common.copyFailed", {
          label: t("adminSettings.qqBinding.secretLabel"),
        }),
      )
      return
    }
    showSuccessToast(
      t("common.copied", { label: t("adminSettings.qqBinding.secretLabel") }),
    )
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader title={t("adminSettings.title")} />
      <AdminControlsCard className="max-w-3xl">
        <div className="space-y-6">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-lg font-semibold">
                {t("adminSettings.qqBinding.title")}
              </h2>
              {configured ? (
                <Badge variant="default">
                  <ShieldCheck />
                  {t("adminSettings.qqBinding.status.configured")}
                </Badge>
              ) : (
                <Badge variant="secondary">
                  {t("adminSettings.qqBinding.status.unconfigured")}
                </Badge>
              )}
            </div>
            <p className="max-w-2xl text-sm text-muted-foreground">
              {t("adminSettings.qqBinding.description")}
            </p>
          </div>

          {configured ? (
            <div className="space-y-3 border-y py-5 text-sm">
              <div className="flex flex-wrap gap-x-8 gap-y-2 text-muted-foreground">
                <span>
                  {t("adminSettings.qqBinding.createdAt")}:{" "}
                  <FormattedDateTime
                    value={statusQuery.data?.created_at}
                    fallback={t("common.notAvailable")}
                  />
                </span>
                <span>
                  {t("adminSettings.qqBinding.updatedAt")}:{" "}
                  <FormattedDateTime
                    value={statusQuery.data?.updated_at}
                    fallback={t("common.notAvailable")}
                  />
                </span>
              </div>
              {secret === null ? (
                <div className="flex items-center gap-3 font-mono text-muted-foreground">
                  <span>••••••••••••••••••••••••</span>
                  <LoadingButton
                    variant="outline"
                    size="sm"
                    loading={revealMutation.isPending}
                    onClick={() => revealMutation.mutate()}
                  >
                    <Eye />
                    {t("adminSettings.qqBinding.actions.reveal")}
                  </LoadingButton>
                </div>
              ) : (
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input
                    value={secret}
                    readOnly
                    aria-label={t("adminSettings.qqBinding.secretLabel")}
                    className="font-mono text-xs"
                    data-testid="admin-qq-binding-secret"
                  />
                  <Button
                    variant="outline"
                    onClick={() => void copySecret()}
                    data-testid="admin-qq-binding-secret-copy-button"
                  >
                    <Copy />
                    {t("common.copy")}
                  </Button>
                </div>
              )}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {!configured ? (
              <LoadingButton
                loading={generateMutation.isPending}
                onClick={() => generateMutation.mutate()}
              >
                <ShieldCheck />
                {t("adminSettings.qqBinding.actions.generate")}
              </LoadingButton>
            ) : (
              <>
                <Button
                  variant="outline"
                  disabled={pending}
                  onClick={() => setConfirmationAction("rotate")}
                >
                  <RotateCw />
                  {t("adminSettings.qqBinding.actions.rotate")}
                </Button>
                <Button
                  variant="destructive"
                  disabled={pending}
                  onClick={() => setConfirmationAction("revoke")}
                >
                  <Trash2 />
                  {t("adminSettings.qqBinding.actions.revoke")}
                </Button>
              </>
            )}
          </div>
        </div>
      </AdminControlsCard>

      <Dialog
        open={confirmationAction !== null}
        onOpenChange={(open) => !open && setConfirmationAction(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t(
                `adminSettings.qqBinding.confirm.${confirmationAction ?? "rotate"}.title`,
              )}
            </DialogTitle>
            <DialogDescription>
              {t(
                `adminSettings.qqBinding.confirm.${confirmationAction ?? "rotate"}.description`,
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmationAction(null)}
            >
              {t("common.cancel")}
            </Button>
            <LoadingButton
              variant={
                confirmationAction === "revoke" ? "destructive" : "default"
              }
              loading={rotateMutation.isPending || revokeMutation.isPending}
              onClick={() =>
                confirmationAction === "rotate"
                  ? rotateMutation.mutate()
                  : revokeMutation.mutate()
              }
            >
              {t(
                `adminSettings.qqBinding.confirm.${confirmationAction ?? "rotate"}.confirm`,
              )}
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
