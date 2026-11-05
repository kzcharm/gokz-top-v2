import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Eye, EyeOff } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  getProfileHiddenMapsQueryOptions,
  hideProfileMap,
  unhideProfileMap,
} from "@/components/Profile/profile-utils"
import { Button } from "@/components/ui/button"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import useAuth from "@/hooks/useAuth"

const EMPTY_IDS = new Set<number>()

export function useHiddenMaps(enabled = true) {
  const { user } = useAuth()
  const { t } = useTranslation()
  const client = useQueryClient()
  const active = enabled && !!user
  const options = getProfileHiddenMapsQueryOptions({
    enabled: active,
    playerId: user?.steamid64 ?? null,
  })
  const query = useQuery(options)
  const mutation = useMutation({
    onMutate: () => options.queryKey,
    mutationFn: ({ mapId, hidden }: { mapId: number; hidden: boolean }) =>
      hidden ? hideProfileMap(mapId) : unhideProfileMap(mapId),
    onSuccess: async (_, { mapId, hidden }, queryKey) => {
      client.setQueryData<Set<number>>(queryKey, (previous) => {
        const next = new Set(previous)
        if (hidden) next.add(mapId)
        else next.delete(mapId)
        return next
      })
      await client.invalidateQueries({ queryKey })
      toast.success(
        t(hidden ? "profile.hiddenMaps.hidden" : "profile.hiddenMaps.unhidden"),
        {
          action: {
            label: t("profile.hiddenMaps.undo"),
            onClick: () => {
              if (
                client.getQueryData<{ steamid64: string }>(["currentUser"])
                  ?.steamid64 !== queryKey[1]
              )
                return
              mutation.mutate({ mapId, hidden: !hidden })
            },
          },
        },
      )
    },
    onError: (_, { hidden }) =>
      toast.error(
        t(
          hidden
            ? "profile.hiddenMaps.hideFailed"
            : "profile.hiddenMaps.unhideFailed",
        ),
      ),
  })
  const ids = active ? (query.data ?? EMPTY_IDS) : EMPTY_IDS
  return {
    ids,
    loading: active && query.isPending,
    error: active && query.isError,
    retry: () => void query.refetch(),
    pending: mutation.isPending,
    hide: (mapId: number) => mutation.mutate({ mapId, hidden: true }),
    unhide: (mapId: number) => mutation.mutate({ mapId, hidden: false }),
    menuItem: (mapId: number) =>
      active ? (
        <DropdownMenuItem
          disabled={mutation.isPending || query.isPending || query.isError}
          onSelect={() => mutation.mutate({ mapId, hidden: !ids.has(mapId) })}
        >
          {ids.has(mapId) ? <Eye /> : <EyeOff />}
          {t(
            ids.has(mapId)
              ? "profile.hiddenMaps.unhideAction"
              : "profile.hiddenMaps.hideAction",
          )}
        </DropdownMenuItem>
      ) : null,
  }
}

export function HiddenMapsStatus({
  state,
}: {
  state: ReturnType<typeof useHiddenMaps>
}) {
  const { t } = useTranslation()
  if (state.error)
    return (
      <div role="alert">
        {t("profile.hiddenMaps.loadFailed")}{" "}
        <Button variant="outline" onClick={state.retry}>
          {t("profile.hiddenMaps.retry")}
        </Button>
      </div>
    )
  if (state.loading) return <output>{t("profile.hiddenMaps.loading")}</output>
  return null
}
