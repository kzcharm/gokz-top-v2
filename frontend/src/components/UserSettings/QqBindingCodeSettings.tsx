import { useMutation } from "@tanstack/react-query"
import { CircleHelp, Copy } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { MeService } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import useCustomToast from "@/hooks/useCustomToast"
import { extractErrorMessage } from "@/utils"

type QQBindingCodeResponse = {
  code: string
  expires_at: string
}

export default function QqBindingCodeSettings() {
  const { t } = useTranslation()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [_copiedValue, copyToClipboard] = useCopyToClipboard()
  const [bindingCode, setBindingCode] = useState<QQBindingCodeResponse | null>(
    null,
  )

  const generateMutation = useMutation({
    mutationFn: () => MeService.createCurrentPlayerQqBindingCode(),
    onSuccess: (data) => {
      setBindingCode(data)
      showSuccessToast(t("settings.profile.qqBinding.toast.generated"))
    },
    onError: (error) => {
      showErrorToast(extractErrorMessage(error))
    },
  })

  const handleCopy = async () => {
    if (bindingCode === null) {
      return
    }

    const success = await copyToClipboard(bindingCode.code)
    if (!success) {
      showErrorToast(
        t("common.copyFailed", {
          label: t("settings.profile.qqBinding.codeLabel"),
        }),
      )
      return
    }

    showSuccessToast(
      t("common.copied", {
        label: t("settings.profile.qqBinding.codeLabel"),
      }),
    )
  }

  return (
    <div className="max-w-2xl">
      <Card>
        <CardHeader className="gap-2">
          <CardTitle className="flex items-center gap-1.5">
            <span>{t("settings.profile.qqBinding.title")}</span>
            <Tooltip delayDuration={150}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className="text-muted-foreground transition-colors hover:text-foreground"
                  aria-label={t("settings.profile.qqBinding.tooltipAriaLabel")}
                >
                  <CircleHelp className="size-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent sideOffset={8} className="max-w-64">
                {t("settings.profile.qqBinding.tooltip")}
              </TooltipContent>
            </Tooltip>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <LoadingButton
              type="button"
              loading={generateMutation.isPending}
              onClick={() => generateMutation.mutate()}
            >
              {t("settings.profile.qqBinding.actions.generate")}
            </LoadingButton>
          </div>
          {bindingCode ? (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                {t("settings.profile.qqBinding.codeLabel")}
              </p>
              <div className="flex w-fit max-w-full items-center gap-1 rounded-md bg-muted py-1 pl-3 pr-1">
                <output
                  id="settings-qq-binding-code"
                  aria-label={t("settings.profile.qqBinding.codeLabel")}
                  className="overflow-x-auto py-1 font-mono text-sm whitespace-nowrap"
                  data-testid="settings-qq-binding-code"
                >
                  {bindingCode.code}
                </output>
                <Tooltip delayDuration={150}>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => void handleCopy()}
                      aria-label={t("common.copy")}
                      data-testid="settings-qq-binding-copy-button"
                    >
                      <Copy className="size-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{t("common.copy")}</TooltipContent>
                </Tooltip>
              </div>
              <div className="text-sm text-muted-foreground">
                <span>{t("settings.profile.qqBinding.expiresAt")} </span>
                <FormattedDateTime
                  value={bindingCode.expires_at}
                  display="relative"
                  fallback={t("common.notAvailable")}
                />
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
