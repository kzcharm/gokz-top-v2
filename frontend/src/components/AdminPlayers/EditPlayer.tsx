import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Check, ChevronDown, Pencil, X } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { PlayersService, type PlayerUpdate } from "@/client"
import {
  CountryFlag,
  countryOptions,
  getCountryName,
} from "@/components/Common/CountryFlag"
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
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
import { cn } from "@/lib/utils"
import { handleError } from "@/utils"

const formSchema = z.object({
  alias: z.string().max(25, "Alias must be 25 characters or fewer"),
  country: z
    .string()
    .max(2, "Country must be a 2-letter code")
    .refine(
      (value) => {
        const normalized = value.trim()
        return normalized.length === 0 || normalized.length === 2
      },
      "Country must be a 2-letter ISO code",
    ),
})

type FormData = z.infer<typeof formSchema>

type EditablePlayer = {
  alias?: string | null
  country?: string | null
  name: string
  steamid64: string
}

function buildDefaultValues(player: EditablePlayer): { alias: string; country: string } {
  return {
    alias: player.alias ?? "",
    country: player.country ?? "",
  }
}

export default function EditPlayer({ player }: { player: EditablePlayer }) {
  const [isOpen, setIsOpen] = useState(false)
  const [countryQuery, setCountryQuery] = useState("")
  const [countryMenuOpen, setCountryMenuOpen] = useState(false)
  const countrySearchRef = useRef<HTMLInputElement | null>(null)
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

  useEffect(() => {
    if (!countryMenuOpen) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      countrySearchRef.current?.focus()
    }, 0)

    return () => window.clearTimeout(timeoutId)
  }, [countryMenuOpen])

  const filteredCountries = useMemo(() => {
    const normalizedQuery = countryQuery.trim().toLowerCase()
    if (normalizedQuery.length === 0) {
      return countryOptions
    }

    return countryOptions.filter((option) => {
      return (
        option.countryCode.toLowerCase().includes(normalizedQuery) ||
        option.name.toLowerCase().includes(normalizedQuery)
      )
    })
  }, [countryQuery])

  const mutation = useMutation({
    mutationFn: (data: PlayerUpdate) =>
      PlayersService.updatePlayer({
        steamid64: player.steamid64,
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
      void queryClient.invalidateQueries({ queryKey: ["leaderboards", "players"] })
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
          setCountryQuery("")
          setCountryMenuOpen(false)
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
                      <DropdownMenu
                        modal={false}
                        open={countryMenuOpen}
                        onOpenChange={setCountryMenuOpen}
                      >
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            className={cn(
                              "border-input focus-visible:border-ring focus-visible:ring-ring/50 flex h-11 w-full items-center justify-between rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-[3px]",
                              countryMenuOpen && "border-ring ring-ring/50 ring-[3px]",
                            )}
                          >
                            <span className="flex min-w-0 items-center gap-2">
                              {field.value.length > 0 ? (
                                <>
                                  <CountryFlag
                                    countryCode={field.value}
                                    showTooltip={false}
                                  />
                                  <span className="truncate">
                                    {getCountryName(field.value) || field.value}
                                  </span>
                                </>
                              ) : (
                                <span className="text-muted-foreground">
                                  Select a country
                                </span>
                              )}
                            </span>
                            <ChevronDown className="text-muted-foreground size-4 shrink-0" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                          align="start"
                          avoidCollisions={false}
                          className="w-[var(--radix-dropdown-menu-trigger-width)] overflow-hidden rounded-xl p-0"
                          side="bottom"
                          sideOffset={8}
                        >
                          <div className="border-b p-3">
                            <Input
                              ref={countrySearchRef}
                              value={countryQuery}
                              maxLength={50}
                              onChange={(event) =>
                                setCountryQuery(event.target.value)
                              }
                              onKeyDown={(event) => event.stopPropagation()}
                              placeholder="Search a country"
                            />
                          </div>
                          <div className="max-h-72 overflow-y-auto py-1">
                            <button
                              type="button"
                              className="hover:bg-accent hover:text-accent-foreground flex w-full items-center gap-3 px-3 py-2 text-left text-sm"
                              onClick={() => {
                                field.onChange("")
                                setCountryMenuOpen(false)
                                setCountryQuery("")
                              }}
                            >
                              <X className="text-muted-foreground size-4" />
                              <span>Clear country</span>
                            </button>
                            {filteredCountries.map((option) => {
                              const selected = field.value === option.countryCode
                              return (
                                <button
                                  key={option.countryCode}
                                  type="button"
                                  className={cn(
                                    "hover:bg-accent hover:text-accent-foreground flex w-full items-center gap-3 px-3 py-2 text-left text-sm",
                                    selected && "text-primary",
                                  )}
                                  onClick={() => {
                                    field.onChange(option.countryCode)
                                    setCountryMenuOpen(false)
                                    setCountryQuery("")
                                  }}
                                >
                                  <CountryFlag
                                    countryCode={option.countryCode}
                                    showTooltip={false}
                                  />
                                  <span className="min-w-0 flex-1 truncate">
                                    {option.name}
                                  </span>
                                  {selected ? (
                                    <Check className="size-4 shrink-0" />
                                  ) : null}
                                </button>
                              )
                            })}
                            {filteredCountries.length === 0 ? (
                              <div className="text-muted-foreground px-3 py-6 text-sm">
                                No countries found.
                              </div>
                            ) : null}
                          </div>
                        </DropdownMenuContent>
                      </DropdownMenu>
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
