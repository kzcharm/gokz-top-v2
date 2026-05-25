import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Pencil } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import {
  type UserPublic,
  type UserRole,
  UsersService,
  type UserUpdate,
} from "@/client"
import { UserRoleBadge } from "@/components/Admin/UserRoleBadge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogClose,
  DialogContent,
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
} from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { USER_ROLE_OPTIONS } from "@/lib/user-roles"
import { handleError } from "@/utils"

const formSchema = z.object({
  roles: z.array(z.enum(["superuser", "admin", "map_admin", "server_owner"])),
  is_active: z.boolean(),
})

type FormData = z.infer<typeof formSchema>

interface EditUserProps {
  user: UserPublic
  onSuccess: () => void
}

const EditUser = ({ user, onSuccess }: EditUserProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      roles: user.roles,
      is_active: user.is_active ?? true,
    },
  })

  const mutation = useMutation({
    mutationFn: (data: UserUpdate) =>
      UsersService.updateUser({ userId: user.steamid64, requestBody: data }),
    onSuccess: () => {
      showSuccessToast("User updated successfully")
      setIsOpen(false)
      onSuccess()
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const onSubmit = (data: FormData) => {
    mutation.mutate(data)
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuItem
        onSelect={(e) => e.preventDefault()}
        onClick={() => {
          form.reset({
            roles: user.roles,
            is_active: user.is_active ?? true,
          })
          setIsOpen(true)
        }}
      >
        <Pencil />
        Edit User
      </DropdownMenuItem>
      <DialogContent className="sm:max-w-md">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <DialogHeader>
              <DialogTitle>Edit User</DialogTitle>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <FormField
                control={form.control}
                name="roles"
                render={({ field }) => (
                  <FormItem className="gap-3">
                    <FormLabel>Roles</FormLabel>
                    <div className="grid gap-3">
                      {USER_ROLE_OPTIONS.map((roleOption) => {
                        const checked = field.value.includes(roleOption.value)
                        return (
                          <div
                            key={roleOption.value}
                            className="flex items-center gap-3 rounded-md border p-3"
                          >
                            <FormControl>
                              <Checkbox
                                aria-label={`${roleOption.label} role`}
                                checked={checked}
                                onCheckedChange={(nextChecked) => {
                                  const nextRoles = nextChecked
                                    ? [...field.value, roleOption.value]
                                    : field.value.filter(
                                        (role) => role !== roleOption.value,
                                      )
                                  field.onChange(nextRoles as UserRole[])
                                }}
                              />
                            </FormControl>
                            <UserRoleBadge role={roleOption.value} />
                          </div>
                        )
                      })}
                    </div>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex items-center gap-3 space-y-0">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <FormLabel className="font-normal">Is active?</FormLabel>
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" disabled={mutation.isPending}>
                  Cancel
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={mutation.isPending}>
                Save
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default EditUser
