import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
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
import { extractErrorMessage } from "@/utils"

const formSchema = z.object({
  address: z
    .string()
    .trim()
    .min(1, { message: "Server address is required" })
    .refine((value) => {
      const separatorIndex = value.lastIndexOf(":")
      if (separatorIndex <= 0 || separatorIndex === value.length - 1) {
        return false
      }

      const port = Number(value.slice(separatorIndex + 1))
      return Number.isInteger(port) && port >= 1 && port <= 65535
    }, "Use the server address format IP:port"),
})

type FormData = z.infer<typeof formSchema>

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
  const [open, setOpen] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const { loginWithSteam } = useAuth()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const authenticated = isLoggedIn()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      address: "",
    },
  })

  const mutation = useMutation({
    mutationFn: async ({ address }: FormData) => {
      const { ip, port } = splitServerAddress(address)
      return await ServersService.createServer({
        requestBody: {
          ip,
          port,
          enabled: true,
        },
      })
    },
    onSuccess: (server) => {
      onServerAdded(server)
      showSuccessToast("Server added to the public browser.")
      setSubmitError(null)
      form.reset()
      setOpen(false)
    },
    onError: (error: ApiError) => {
      const message = extractErrorMessage(error)
      setSubmitError(message)
      showErrorToast(message)
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
          aria-label="Add server"
          title={authenticated ? "Add server" : "Login to add a server"}
          data-testid="add-server-button"
        >
          <Plus className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Server</DialogTitle>
          <DialogDescription>
            {authenticated
              ? "You can only add GOKZ server"
              : "Log in with Steam to add a public server. You can only add GOKZ server."}
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
                      Server address <span className="text-destructive">*</span>
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
                  <AlertTitle>Add failed</AlertTitle>
                  <AlertDescription>{submitError}</AlertDescription>
                </Alert>
              ) : null}

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => handleOpenChange(false)}
                  disabled={mutation.isPending}
                >
                  Cancel
                </Button>
                <LoadingButton type="submit" loading={mutation.isPending}>
                  Add
                </LoadingButton>
              </DialogFooter>
            </form>
          </Form>
        ) : (
          <>
            <Alert>
              <AlertTitle>Login required</AlertTitle>
              <AlertDescription>
                You need to log in with Steam before adding a server.
              </AlertDescription>
            </Alert>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
              <Button type="button" onClick={loginWithSteam}>
                Continue with Steam
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
