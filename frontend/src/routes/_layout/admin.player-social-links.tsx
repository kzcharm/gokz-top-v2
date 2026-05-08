import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import {
  type AdminPlayerSocialLinkPublic,
  AdminPlayerSocialLinksService,
  type PlayerSocialPlatform,
  UsersService,
} from "@/client"
import {
  AdminControlsCard,
  AdminPageHeader,
  AdminTableCard,
} from "@/components/Admin/AdminPageLayout"
import { DataTable } from "@/components/Common/DataTable"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { getPageTitle } from "@/lib/site"
import {
  getSocialPlatformLabel,
  SocialPlatformIcon,
  socialPlatformOrder,
} from "@/lib/social-links"
import { isSuperuser } from "@/lib/user-roles"
import { handleError } from "@/utils"

type LinkDialogState =
  | { mode: "create"; link: null }
  | { mode: "edit"; link: AdminPlayerSocialLinkPublic }

export const Route = createFileRoute("/_layout/admin/player-social-links")({
  component: AdminPlayerSocialLinks,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
    const user = await UsersService.readUserMe().catch(() => {
      localStorage.removeItem("access_token")
      throw redirect({
        to: "/login",
      })
    })
    if (!isSuperuser(user)) {
      throw redirect({
        to: "/",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: getPageTitle(),
      },
    ],
  }),
})

function LinkDialog({
  state,
  open,
  onOpenChange,
}: {
  state: LinkDialogState
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [steamid64, setSteamid64] = useState("")
  const [url, setUrl] = useState("")
  const [verified, setVerified] = useState(false)

  useEffect(() => {
    if (!open) {
      return
    }
    if (state.mode === "create") {
      setSteamid64("")
      setUrl("")
      setVerified(false)
      return
    }
    setSteamid64(state.link.player_steamid64)
    setUrl(state.link.url)
    setVerified(state.link.verified)
  }, [open, state])

  const createMutation = useMutation({
    mutationFn: () =>
      AdminPlayerSocialLinksService.createAdminPlayerSocialLink({
        requestBody: {
          player_steamid64: steamid64.trim(),
          url: url.trim(),
          verified,
        },
      }),
    onSuccess: () => {
      showSuccessToast("Social link added")
      onOpenChange(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-social-links"] })
      void queryClient.invalidateQueries({ queryKey: ["player-social-links"] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: () =>
      state.mode === "edit"
        ? AdminPlayerSocialLinksService.updateAdminPlayerSocialLink({
            linkId: state.link.id,
            requestBody: {
              url: url.trim(),
              verified,
            },
          })
        : Promise.reject(new Error("No social link selected")),
    onSuccess: () => {
      showSuccessToast("Social link updated")
      onOpenChange(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-social-links"] })
      void queryClient.invalidateQueries({ queryKey: ["player-social-links"] })
    },
  })

  const pending = createMutation.isPending || updateMutation.isPending
  const submit = () => {
    if (state.mode === "create") {
      createMutation.mutate()
      return
    }
    updateMutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {state.mode === "create" ? "Add Social Link" : "Edit Social Link"}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <label className="text-sm font-medium" htmlFor="social-steamid64">
              Steam ID64
            </label>
            <Input
              id="social-steamid64"
              value={steamid64}
              disabled={state.mode === "edit"}
              onChange={(event) => setSteamid64(event.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium" htmlFor="social-url">
              URL
            </label>
            <Input
              id="social-url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
            />
          </div>
          {state.mode === "create" ? (
            <label
              className="flex items-center gap-3 text-sm font-medium"
              htmlFor="social-verified"
            >
              <Switch
                id="social-verified"
                checked={verified}
                onCheckedChange={setVerified}
              />
              Verified
            </label>
          ) : null}
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" disabled={pending}>
              Cancel
            </Button>
          </DialogClose>
          <LoadingButton loading={pending} type="button" onClick={submit}>
            Save
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AdminPlayerSocialLinks() {
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [steamid64, setSteamid64] = useState("")
  const [platform, setPlatform] = useState<PlayerSocialPlatform | "all">("all")
  const [verified, setVerified] = useState<"all" | "true" | "false">("all")
  const [dialogState, setDialogState] = useState<LinkDialogState>({
    mode: "create",
    link: null,
  })
  const [dialogOpen, setDialogOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()

  const { data, isLoading } = useQuery({
    queryKey: [
      "admin-social-links",
      pageIndex,
      pageSize,
      steamid64.trim(),
      platform,
      verified,
    ],
    queryFn: () =>
      AdminPlayerSocialLinksService.readAdminPlayerSocialLinks({
        offset: pageIndex * pageSize,
        limit: pageSize,
        steamid64: steamid64.trim() || null,
        platform: platform === "all" ? null : platform,
        verified: verified === "all" ? null : verified === "true",
      }),
  })

  const deleteMutation = useMutation({
    mutationFn: (linkId: string) =>
      AdminPlayerSocialLinksService.deleteAdminPlayerSocialLink({ linkId }),
    onSuccess: () => {
      showSuccessToast("Social link deleted")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-social-links"] })
      void queryClient.invalidateQueries({ queryKey: ["player-social-links"] })
    },
  })

  const toggleVerifiedMutation = useMutation({
    mutationFn: ({
      linkId,
      verified,
    }: {
      linkId: string
      verified: boolean
    }) =>
      AdminPlayerSocialLinksService.updateAdminPlayerSocialLink({
        linkId,
        requestBody: { verified },
      }),
    onSuccess: () => {
      showSuccessToast("Verification updated")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-social-links"] })
      void queryClient.invalidateQueries({ queryKey: ["player-social-links"] })
    },
  })

  const columns = useMemo<ColumnDef<AdminPlayerSocialLinkPublic>[]>(
    () => [
      {
        accessorKey: "player",
        header: "Player",
        cell: ({ row }) => (
          <PlayerDisplay
            player={row.original.player}
            fallbackSteamid64={row.original.player_steamid64}
          />
        ),
      },
      {
        accessorKey: "platform",
        header: "Platform",
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <SocialPlatformIcon
              platform={row.original.platform}
              className="size-4"
            />
            {getSocialPlatformLabel(row.original.platform)}
          </div>
        ),
      },
      {
        accessorKey: "account_identifier",
        header: "Account",
        cell: ({ row }) => (
          <a
            href={row.original.url}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-sm text-primary hover:underline"
          >
            {row.original.account_identifier}
          </a>
        ),
      },
      {
        accessorKey: "verified",
        header: "Verified",
        cell: ({ row }) => {
          const isPending =
            toggleVerifiedMutation.isPending &&
            toggleVerifiedMutation.variables?.linkId === row.original.id

          return (
            <Switch
              checked={row.original.verified}
              disabled={isPending}
              onCheckedChange={(nextVerified) => {
                toggleVerifiedMutation.mutate({
                  linkId: row.original.id,
                  verified: nextVerified,
                })
              }}
              aria-label={`Toggle verification for ${row.original.account_identifier}`}
            />
          )
        },
      },
      {
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => {
                setDialogState({ mode: "edit", link: row.original })
                setDialogOpen(true)
              }}
              aria-label="Edit social link"
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="text-destructive hover:text-destructive"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate(row.original.id)}
              aria-label="Delete social link"
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ),
      },
    ],
    [deleteMutation, toggleVerifiedMutation],
  )

  return (
    <div className="flex flex-col gap-6">
      <AdminPageHeader title="Player Social Links" />
      <AdminControlsCard>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <Input
            aria-label="Filter by Steam ID64"
            className="sm:w-56"
            placeholder="Steam ID64"
            value={steamid64}
            onChange={(event) => {
              setSteamid64(event.target.value)
              setPageIndex(0)
            }}
          />
          <Select
            value={platform}
            onValueChange={(value) => {
              setPlatform(value as PlayerSocialPlatform | "all")
              setPageIndex(0)
            }}
          >
            <SelectTrigger className="sm:w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All platforms</SelectItem>
              {socialPlatformOrder.map((platformOption) => (
                <SelectItem key={platformOption} value={platformOption}>
                  {getSocialPlatformLabel(platformOption)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={verified}
            onValueChange={(value) => {
              setVerified(value as "all" | "true" | "false")
              setPageIndex(0)
            }}
          >
            <SelectTrigger className="sm:w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="true">Verified</SelectItem>
              <SelectItem value="false">Unverified</SelectItem>
            </SelectContent>
          </Select>
          <Button
            type="button"
            onClick={() => {
              setDialogState({ mode: "create", link: null })
              setDialogOpen(true)
            }}
          >
            <Plus className="size-4" />
            Add
          </Button>
        </div>
      </AdminControlsCard>
      <AdminTableCard>
        <DataTable
          columns={columns}
          data={data?.data ?? []}
          isLoading={isLoading}
          stickyHeader
          stickyHeaderTopClassName="top-16"
          tableContainerClassName="md:overflow-visible"
          tableClassName="border-separate border-spacing-0"
          showFooter={false}
          emptyText="No social links found."
          serverPagination={{
            pageIndex,
            pageSize,
            totalCount: data?.count ?? 0,
            onPageChange: setPageIndex,
            onPageSizeChange: (size) => {
              setPageSize(size)
              setPageIndex(0)
            },
          }}
        />
        <TablePaginationFooter
          totalLabel="Links"
          totalCount={data?.count ?? 0}
          pageIndex={pageIndex}
          pageCount={Math.max(1, Math.ceil((data?.count ?? 0) / pageSize))}
          pageSize={pageSize}
          onPageIndexChange={setPageIndex}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPageIndex(0)
          }}
          hasExactCount={!isLoading}
          isTotalCountLoading={isLoading}
        />
      </AdminTableCard>
      <LinkDialog
        state={dialogState}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  )
}
