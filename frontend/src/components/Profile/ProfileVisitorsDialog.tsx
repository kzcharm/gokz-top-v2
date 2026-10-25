import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import type { PlayerRefPublic } from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"

type VisitorsPage = {
  data: {
    player: PlayerRefPublic
    viewed_at: string | null
    view_date: string
  }[]
  count: number
}

export function ProfileVisitorsDialog({
  identifier,
  open,
  onOpenChange,
}: {
  identifier: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "profile-visitors-page-size",
  })
  const query = useQuery({
    queryKey: ["profile-visitors", identifier, pageIndex, pageSize],
    enabled: open,
    retry: false,
    queryFn: async ({ signal }): Promise<VisitorsPage> => {
      const accessToken = localStorage.getItem("access_token")
      const response = await fetch(
        `${OpenAPI.BASE}/v1/players/${encodeURIComponent(identifier)}/views/players?offset=${pageIndex * pageSize}&limit=${pageSize}`,
        {
          signal,
          credentials: OpenAPI.CREDENTIALS,
          headers: accessToken
            ? { Authorization: `Bearer ${accessToken}` }
            : {},
        },
      )
      if (!response.ok) throw new Error("Could not load profile visitors")
      return response.json()
    },
  })
  const pageCount = Math.max(1, Math.ceil((query.data?.count ?? 0) / pageSize))
  useEffect(() => {
    if (query.data)
      setPageIndex((previous) => Math.min(previous, pageCount - 1))
  }, [query.data, pageCount])
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[85vh] overflow-y-auto sm:max-w-2xl"
        data-testid="profile-visitors-dialog"
        aria-describedby={undefined}
      >
        <DialogHeader>
          <DialogTitle>{t("profile.visitors.title")}</DialogTitle>
        </DialogHeader>
        {query.isLoading ? (
          <output>{t("common.loading")}</output>
        ) : query.isError ? (
          <p role="alert">{t("profile.visitors.loadFailed")}</p>
        ) : query.data?.data.length ? (
          <div className="space-y-2">
            {query.data.data.map((entry) => (
              <div
                key={`${entry.player.steamid64}-${entry.view_date}`}
                className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/70 p-3"
                data-testid="profile-visitor-row"
              >
                <PlayerDisplay player={entry.player} />
                <span className="text-xs text-muted-foreground">
                  <FormattedDateTime
                    value={entry.viewed_at ?? `${entry.view_date}T12:00:00`}
                    dateOnly={!entry.viewed_at}
                    display="relative"
                    tickerMs={60_000}
                  />
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p>{t("profile.visitors.empty")}</p>
        )}
        {query.data ? (
          <TablePaginationFooter
            totalLabel={t("profile.summary.profileViews")}
            totalCount={query.data.count}
            pageIndex={pageIndex}
            pageCount={pageCount}
            pageSize={pageSize}
            onPageIndexChange={setPageIndex}
            onPageSizeChange={(size) => {
              setPageSize(size)
              setPageIndex(0)
            }}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
