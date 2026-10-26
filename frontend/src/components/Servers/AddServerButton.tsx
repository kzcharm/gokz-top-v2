import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import type { TFunction } from "i18next"
import { Plus } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import { type ApiError, type ServerPublic, ServersService } from "@/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"

const createFormSchema = (t: TFunction) =>
  z.object({
    address: z
      .string()
      .trim()
      .min(1, { message: t("serverBrowser.addressRequired") })
      .refine((value) => {
        const separatorIndex = value.lastIndexOf(":")
        if (separatorIndex <= 0 || separatorIndex === value.length - 1) {
          return false
        }

        const port = Number(value.slice(separatorIndex + 1))
        return Number.isInteger(port) && port >= 1 && port <= 65535
      }, t("serverBrowser.addressFormat")),
  })

type FormData = z.infer<ReturnType<typeof createFormSchema>>

function splitServerAddress(address: string) {
  const trimmedAddress = address.trim()
  const separatorIndex = trimmedAddress.lastIndexOf(":")

  return {
    ip: trimmedAddress.slice(0, separatorIndex),
    port: Number(trimmedAddress.slice(separatorIndex + 1)),
  }
}

interface AddServerButtonProps {
  onServerAdded: (server: ServerPublic) => void
}

export function AddServerButton({ onServerAdded }: AddServerButtonProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const { loginWithSteam } = useAuth()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const authenticated = isLoggedIn()

  const formSchema = useMemo(() => createFormSchema(t), [t])
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      address: "",
    },
  })

  const hasAddressError = Boolean(form.formState.errors.address)
  // biome-ignore lint/correctness/useExhaustiveDependencies: Revalidate visible errors when the translation function changes with the locale.
  useEffect(() => {
    if (hasAddressError) void form.trigger("address")
  }, [form, hasAddressError, t])

  const mutation = useMutation({
    mutationFn: async ({ address }: FormData) => {
      const { ip, port } = splitServerAddress(address)
      return await ServersService.createServer({
        requestBody: {
          ip,
          port,
          status: "enabled",
        },
      })
    },
    onSuccess: (server) => {
      onServerAdded(server)
      showSuccessToast(t("serverBrowser.added"))
      setSubmitError(null)
      form.reset()
      setOpen(false)
    },
    onError: (error: ApiError) => {
      const errorKey =
        (
          {
            401: "serverBrowser.loginDescription",
            404: "serverBrowser.groupNotFound",
            409: "serverBrowser.alreadyExists",
            422: "serverBrowser.queryError",
          } as Record<number, string>
        )[error.status] ?? "serverBrowser.addError"
      const resolvedErrorKey =
        error.status === 403 &&
        typeof error.body === "object" &&
        error.body !== null &&
        "detail" in error.body &&
        error.body.detail === "Server is disabled"
          ? "serverBrowser.disabled"
          : errorKey
      setSubmitError(resolvedErrorKey)
      showErrorToast(t(resolvedErrorKey))
    },
  })

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (!nextOpen) {
      setSubmitError(null)
      form.reset()
    }
  }

  const handleSubmit = (data: FormData) => {
    setSubmitError(null)
    mutation.mutate(data)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          aria-label={t("serverBrowser.addServer")}
          title={
            authenticated
              ? t("serverBrowser.addServer")
              : t("serverBrowser.loginToAdd")
          }
          data-testid="add-server-button"
        >
          <Plus className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("serverBrowser.addTitle")}</DialogTitle>
          <DialogDescription>
            {authenticated
              ? t("serverBrowser.addDescription")
              : t("serverBrowser.addLoginDescription")}
          </DialogDescription>
        </DialogHeader>

        {authenticated ? (
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(handleSubmit)}
              className="space-y-4"
            >
              <FormField
                control={form.control}
                name="address"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {t("serverBrowser.address")}
                      <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        placeholder="123.45.67.89:27015"
                        autoComplete="off"
                        data-testid="add-server-address-input"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {submitError ? (
                <Alert variant="destructive">
                  <AlertTitle>{t("serverBrowser.addFailed")}</AlertTitle>
                  <AlertDescription>{t(submitError)}</AlertDescription>
                </Alert>
              ) : null}

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => handleOpenChange(false)}
                  disabled={mutation.isPending}
                >
                  {t("common.cancel")}
                </Button>
                <LoadingButton type="submit" loading={mutation.isPending}>
                  {t("common.add")}
                </LoadingButton>
              </DialogFooter>
            </form>
          </Form>
        ) : (
          <>
            <Alert>
              <AlertTitle>{t("serverBrowser.loginRequired")}</AlertTitle>
              <AlertDescription>
                {t("serverBrowser.loginDescription")}
              </AlertDescription>
            </Alert>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setOpen(false)}
              >
                {t("common.cancel")}
              </Button>
              <Button type="button" onClick={loginWithSteam}>
                {t("serverBrowser.continueSteam")}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
