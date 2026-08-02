import { createFileRoute } from "@tanstack/react-router"

import { BansPage } from "@/components/Bans/BansPage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/bans")({
  component: BansRoute,
  validateSearch: (search: Record<string, unknown>) => {
    const banType =
      typeof search.banType === "string" ? search.banType : undefined
    const status = typeof search.status === "string" ? search.status : undefined
    const serverId =
      typeof search.serverId === "string" ? search.serverId : undefined

    return {
      q: typeof search.q === "string" ? search.q : undefined,
      banType,
      status:
        status === "permanent" ||
        status === "active" ||
        status === "expired" ||
        status === "unbanned"
          ? status
          : undefined,
      serverId:
        serverId === "none" ||
        (serverId !== undefined &&
          /^\d+$/.test(serverId) &&
          Number(serverId) > 0)
          ? serverId
          : undefined,
    }
  },
  head: () => ({
    meta: [
      {
        title: getPageTitle("Bans"),
      },
    ],
  }),
})

function BansRoute() {
  const { banType, q, serverId, status } = Route.useSearch()

  return (
    <BansPage
      initialBanType={banType ?? ""}
      initialSearchQuery={q ?? ""}
      initialServerFilter={
        serverId === "none" ? "none" : serverId ? Number(serverId) : null
      }
      initialStatus={
        (status ?? "") as "" | "permanent" | "active" | "expired" | "unbanned"
      }
    />
  )
}
