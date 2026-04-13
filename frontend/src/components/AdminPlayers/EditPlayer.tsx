import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Pencil } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { PlayersService, type PlayerUpdate } from "@/client"
import { CountryPicker } from "@/components/Common/CountryPicker"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
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
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

const formSchema = z.object({
  alias: z.string().max(25, "Alias must be 25 characters or fewer"),
  country: z
    .string()
    .max(2, "Country must be a 2-letter code")
    .refine((value) => {
      const normalized = value.trim()
      return normalized.length === 0 || normalized.length === 2
    }, "Country must be a 2-letter ISO code"),
})

type FormData = z.infer<typeof formSchema>

type EditablePlayer = {
  alias?: string | null
  country?: string | null
  name: string
  steamid64: string
}

function buildDefaultValues(player: EditablePlayer): {
  alias: string
  country: string
} {
  return {
    alias: player.alias ?? "",
    country: player.country ?? "",
  }
}

export default function EditPlayer({ player }: { player: EditablePlayer }) {
  const [isOpen, setIsOpen] = useState(false)
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: buildDefaultValues(player),
  })

  useEffect(() => {
    form.reset(buildDefaultValues(player))
  }, [form, player])

  const mutation = useMutation({
    mutationFn: (data: PlayerUpdate) =>
      PlayersService.updatePlayer({
        identifier: player.steamid64,
        requestBody: data,
      }),
    onSuccess: () => {
      showSuccessToast("Player updated successfully")
      setIsOpen(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["players"] })
      void queryClient.invalidateQueries({ queryKey: ["profile-player"] })
      void queryClient.invalidateQueries({
        queryKey: ["leaderboards", "players"],
      })
    },
  })

  if (!user?.is_superuser) {
    return null
  }

  const onSubmit = (data: FormData) => {
    const alias = data.alias.trim()
    const country = data.country.trim().toUpperCase()

    mutation.mutate({
      alias: alias.length > 0 ? alias : null,
      country: country.length > 0 ? country : null,
    })
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuItem
        onClick={() => {
          form.reset(buildDefaultValues(player))
          setIsOpen(true)
        }}
        onSelect={(event) => event.preventDefault()}
      >
        <Pencil />
        Edit
      </DropdownMenuItem>
      <DialogContent className="sm:max-w-md">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <DialogHeader>
              <DialogTitle>Edit Player</DialogTitle>
              <DialogDescription>
                Update the alias and country for {player.name}.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <FormField
                control={form.control}
                name="alias"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Alias</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        value={field.value ?? ""}
                        maxLength={25}
                        placeholder="Leave blank to clear"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="country"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Country</FormLabel>
                    <FormControl>
                      <CountryPicker
                        value={field.value.length > 0 ? field.value : null}
                        onChange={(value) => field.onChange(value ?? "")}
                        placeholder="Select a country"
                        clearLabel="Clear country"
                        triggerClassName="h-11 bg-transparent"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter>
              <DialogClose asChild>
                <Button disabled={mutation.isPending} variant="outline">
                  Cancel
                </Button>
              </DialogClose>
              <LoadingButton loading={mutation.isPending} type="submit">
                Save
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
