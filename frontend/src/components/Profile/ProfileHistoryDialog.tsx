import { useQuery } from "@tanstack/react-query"
import { History } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { getInitials } from "@/utils"

import { FormattedDateTime } from "../Common/FormattedDateTime"
import { fetchProfileHistory, type ProfileHistoryEntry } from "./profile-utils"

function getHistoryAvatarUrl(entry: ProfileHistoryEntry) {
  if (!entry.avatar_hash) {
    return null
  }

  return `https://avatars.steamstatic.com/${entry.avatar_hash}_full.jpg`
}

function HistoryRow({ entry }: { entry: ProfileHistoryEntry }) {
  const { t } = useTranslation()
  const avatarUrl = getHistoryAvatarUrl(entry)
  const displayName = entry.name?.trim() || t("profile.history.missingName")

  return (
    <div
      className="flex items-center gap-4 rounded-2xl border border-border/70 bg-card/70 p-4"
      data-testid={`profile-history-row-${entry.id}`}
    >
      <Avatar className="size-14 rounded-xl border border-border/60">
        <AvatarImage
          className="object-cover"
          src={avatarUrl ?? undefined}
          alt={displayName}
        />
        <AvatarFallback className="rounded-xl bg-zinc-600 text-sm font-semibold text-white">
          {getInitials(displayName)}
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-foreground">
          {displayName}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          <FormattedDateTime
            value={entry.changed_at}
            fallback={t("profile.unknownDate")}
          />
        </div>
      </div>
    </div>
  )
}

export function ProfileHistoryDialog({
  identifier,
  onOpenChange,
  open,
}: {
  identifier: string
  onOpenChange: (open: boolean) => void
  open: boolean
}) {
  const { t } = useTranslation()
  const historyQuery = useQuery({
    queryKey: ["profile-history", identifier],
    queryFn: () => fetchProfileHistory({ identifier }),
    enabled: open,
    retry: false,
    staleTime: 30_000,
  })
  const rows = historyQuery.data?.data ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[85vh] overflow-y-auto sm:max-w-2xl"
        data-testid="profile-history-dialog"
      >
        <DialogHeader>
          <DialogTitle>{t("profile.history.title")}</DialogTitle>
          <DialogDescription>
            {t("profile.history.description")}
          </DialogDescription>
        </DialogHeader>

        {historyQuery.isLoading ? (
          <div className="space-y-3 py-2">
            {Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-22 rounded-2xl" />
            ))}
          </div>
        ) : historyQuery.isError ? (
          <div className="rounded-2xl border border-dashed border-destructive/40 bg-destructive/5 px-4 py-6 text-sm text-muted-foreground">
            {t("profile.history.loadFailed")}
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border/70 bg-muted/20 px-4 py-8 text-center text-sm text-muted-foreground">
            <div className="mx-auto mb-3 flex size-10 items-center justify-center rounded-full border border-border/70 bg-background/80">
              <History className="size-4" />
            </div>
            {t("profile.history.empty")}
          </div>
        ) : (
          <div className="space-y-3">
            {rows.map((entry) => (
              <HistoryRow key={entry.id} entry={entry} />
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
