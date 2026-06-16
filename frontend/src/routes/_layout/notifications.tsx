import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, redirect } from "@tanstack/react-router"
import {
  Bell,
  Flag,
  Heart,
  MessageCircle,
  ShieldAlert,
  Trophy,
  UserPlus,
} from "lucide-react"
import { type ReactNode, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  MeService,
  type PlayerNotificationPublic,
  type PlayerNotificationType,
  type PlayerRefPublic,
  type RecordType,
} from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { TablePaginationFooter } from "@/components/Common/TablePaginationFooter"
import { formatRecordTime } from "@/components/Records/utils"
import type { AppScope } from "@/components/scope-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { isLoggedIn } from "@/hooks/useAuth"
import { usePersistedPageSize } from "@/hooks/usePersistedPageSize"
import { getPageTitle } from "@/lib/site"
import { cn } from "@/lib/utils"

const NOTIFICATION_PAGE_SIZE_OPTIONS = [10, 20, 50] as const

export const Route = createFileRoute("/_layout/notifications")({
  beforeLoad: () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }

    throw redirect({
      to: "/settings/notifications",
    })
  },
  head: () => ({
    meta: [
      {
        title: getPageTitle("Notifications"),
      },
    ],
  }),
})

type NotificationDisplay = {
  icon: ReactNode
  action: string
  detail: string | null
  actor: PlayerRefPublic | null | undefined
  showActor?: boolean
}

const notificationLinkClassName =
  "rounded-sm font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"

function formatNotificationRecordTime(value: number | null | undefined) {
  return typeof value === "number" ? formatRecordTime(value) : "-"
}

function notificationIcon(type: PlayerNotificationType) {
  if (type === "profile_like") {
    return <Heart className="size-4" />
  }
  if (type === "profile_comment") {
    return <MessageCircle className="size-4" />
  }
  if (type === "player_follow") {
    return <UserPlus className="size-4" />
  }
  if (type === "wr_beaten") {
    return <Trophy className="size-4" />
  }
  if (type === "player_report") {
    return <Flag className="size-4" />
  }
  if (type === "map_review_comment_deleted") {
    return <ShieldAlert className="size-4" />
  }
  return <Bell className="size-4" />
}

function buildNotificationDisplay(
  notification: PlayerNotificationPublic,
  t: ReturnType<typeof useTranslation>["t"],
): NotificationDisplay {
  const mapName = notification.map_name ?? t("notifications.unknownMap")
  const scope = notification.scope ?? "-"
  const recordType = notification.record_type ?? "-"
  const time = formatNotificationRecordTime(notification.new_record_time)

  if (notification.type === "profile_like") {
    return {
      icon: notificationIcon(notification.type),
      action: t("notifications.events.profileLikeAction"),
      detail: null,
      actor: notification.actor,
    }
  }

  if (notification.type === "profile_comment") {
    return {
      icon: notificationIcon(notification.type),
      action: t("notifications.events.profileCommentAction"),
      detail: notification.comment_preview ?? null,
      actor: notification.actor,
    }
  }

  if (notification.type === "player_follow") {
    return {
      icon: notificationIcon(notification.type),
      action: t("notifications.events.playerFollowAction"),
      detail: null,
      actor: notification.actor,
    }
  }

  if (notification.type === "wr_beaten") {
    return {
      icon: notificationIcon(notification.type),
      action: t("notifications.events.wrBeatenAction", {
        map: mapName,
      }),
      detail: t("notifications.events.wrBeatenDetail", {
        scope,
        type: recordType,
        time,
      }),
      actor: notification.actor,
    }
  }

  if (notification.type === "player_report") {
    return {
      icon: notificationIcon(notification.type),
      action: t("notifications.events.playerReportAction"),
      detail: notification.comment_preview ?? null,
      actor: notification.actor,
    }
  }

  if (notification.type === "map_review_comment_deleted") {
    return {
      icon: notificationIcon(notification.type),
      action: t("notifications.events.mapReviewCommentDeletedAction", {
        map: mapName,
      }),
      detail: notification.comment_text ?? notification.comment_preview ?? null,
      actor: null,
      showActor: false,
    }
  }

  return {
    icon: notificationIcon(notification.type),
    action: t("notifications.events.generic"),
    detail: null,
    actor: notification.actor,
  }
}

function NotificationActor({
  actor,
}: {
  actor: PlayerRefPublic | null | undefined
}) {
  const { t } = useTranslation()

  if (!actor) {
    return (
      <span className="font-medium text-sm leading-6">
        {t("notifications.someone")}
      </span>
    )
  }

  return (
    <PlayerDisplay
      player={actor}
      className="min-w-0"
      nameMaxLength={24}
      hideAvatarWithoutSteamid64
    />
  )
}

function ReportNotificationDetails({
  notification,
  onMarkRead,
}: {
  notification: PlayerNotificationPublic
  onMarkRead: () => void
}) {
  const { t } = useTranslation()
  const targetPlayer = notification.target_player
  const targetSteamid64 =
    targetPlayer?.steamid64 ?? notification.target_player_steamid64
  const hasRecordContext =
    notification.new_record_uuid != null ||
    notification.map_name != null ||
    notification.new_record_time != null
  const description = notification.comment_preview

  if (!targetSteamid64 && !hasRecordContext && !description) {
    return null
  }

  const recordDetailParts = [
    notification.scope ?? null,
    notification.record_type ?? null,
    notification.new_record_time != null
      ? formatRecordTime(notification.new_record_time)
      : null,
  ].filter((part): part is string => Boolean(part))
  const canLinkMap =
    notification.map_name != null &&
    isNotificationAppScope(notification.scope) &&
    isNotificationRecordType(notification.record_type)

  return (
    <span className="block space-y-2 text-sm">
      {targetSteamid64 ? (
        <span className="grid gap-1 text-muted-foreground">
          <span>Target:</span>
          <span className="flex min-w-0 pl-4">
            {targetPlayer ? (
              <PlayerDisplay
                player={targetPlayer}
                className="min-w-0 text-foreground"
                nameMaxLength={24}
                hideAvatarWithoutSteamid64
                showSteamid
              />
            ) : (
              <PlayerDisplay
                player={{ steamid64: targetSteamid64 }}
                className="min-w-0 text-foreground"
                nameMaxLength={24}
                hideAvatarWithoutSteamid64
                showSteamid
              />
            )}
          </span>
        </span>
      ) : null}
      {hasRecordContext ? (
        <span className="block text-muted-foreground">
          Record:{" "}
          {notification.map_name ? (
            canLinkMap ? (
              <Link
                to="/maps/$mapName/maptop"
                params={{ mapName: notification.map_name }}
                search={{
                  scope: notification.scope as AppScope,
                  type: notification.record_type as RecordType,
                }}
                className={notificationLinkClassName}
                onClick={onMarkRead}
              >
                {notification.map_name}
              </Link>
            ) : (
              notification.map_name
            )
          ) : (
            t("notifications.events.recordContext")
          )}
          {recordDetailParts.length > 0
            ? ` - ${recordDetailParts.join(" - ")}`
            : ""}
        </span>
      ) : null}
      {description ? (
        <span className="block text-muted-foreground">{description}</span>
      ) : null}
    </span>
  )
}

function isNotificationAppScope(
  scope: PlayerNotificationPublic["scope"],
): scope is AppScope {
  return (
    scope === "OVR" || scope === "KZT" || scope === "SKZ" || scope === "VNL"
  )
}

function isNotificationRecordType(
  recordType: PlayerNotificationPublic["record_type"],
): recordType is RecordType {
  return recordType === "NUB" || recordType === "PRO"
}

function NotificationAction({
  notification,
  display,
  onMarkRead,
}: {
  notification: PlayerNotificationPublic
  display: NotificationDisplay
  onMarkRead: () => void
}) {
  const { t } = useTranslation()

  if (
    notification.type === "wr_beaten" &&
    notification.map_name &&
    isNotificationAppScope(notification.scope) &&
    isNotificationRecordType(notification.record_type)
  ) {
    return (
      <span className="flex min-w-0 flex-wrap items-center gap-x-1.5 text-sm leading-6">
        <button
          type="button"
          className="rounded-sm text-left hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          onClick={onMarkRead}
        >
          {t("notifications.events.wrBeatenActionPrefix")}
        </button>
        <Link
          to="/maps/$mapName/maptop"
          params={{ mapName: notification.map_name }}
          search={{
            scope: notification.scope,
            type: notification.record_type,
          }}
          className={notificationLinkClassName}
          onClick={onMarkRead}
        >
          {notification.map_name}
        </Link>
        <span>{t("notifications.events.wrBeatenActionSuffix")}</span>
      </span>
    )
  }

  if (notification.type === "map_review_comment_deleted") {
    return (
      <span className="flex min-w-0 flex-wrap items-center gap-x-1.5 text-sm leading-6">
        <button
          type="button"
          className="rounded-sm text-left hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          onClick={onMarkRead}
        >
          {t("notifications.events.mapReviewCommentDeletedActionPrefix")}
        </button>
        {notification.map_name ? (
          <Link
            to="/maps/$mapName/reviews"
            params={{ mapName: notification.map_name }}
            className={notificationLinkClassName}
            onClick={onMarkRead}
          >
            {notification.map_name}
          </Link>
        ) : (
          <span>{t("notifications.unknownMap")}</span>
        )}
        <span>
          {t("notifications.events.mapReviewCommentDeletedActionSuffix")}
        </span>
      </span>
    )
  }

  return (
    <button
      type="button"
      className="rounded-sm text-left text-sm leading-6 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      onClick={onMarkRead}
    >
      {display.action}
    </button>
  )
}

export function NotificationsRoute() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = usePersistedPageSize({
    storageKey: "gokz-page-size-notifications",
    pageSizeOptions: NOTIFICATION_PAGE_SIZE_OPTIONS,
  })
  const offset = pageIndex * pageSize
  const notificationsQuery = useQuery({
    queryKey: ["me", "notifications", { offset, limit: pageSize }],
    queryFn: () =>
      MeService.readCurrentPlayerNotifications({
        offset,
        limit: pageSize,
      }),
    placeholderData: (previousData) => previousData,
  })
  const unreadCountQuery = useQuery({
    queryKey: ["me", "notifications", "unread-count"],
    queryFn: MeService.readCurrentPlayerNotificationUnreadCount,
  })
  const unreadCount = unreadCountQuery.data?.unread_count ?? 0
  const totalCount = notificationsQuery.data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize))

  useEffect(() => {
    if (pageIndex <= pageCount - 1) {
      return
    }
    setPageIndex(pageCount - 1)
  }, [pageCount, pageIndex])

  const invalidateNotifications = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["me", "notifications"] }),
      queryClient.invalidateQueries({
        queryKey: ["me", "notifications", "unread-count"],
      }),
    ])
  }

  const markReadMutation = useMutation({
    mutationFn: (notificationId: string) =>
      MeService.markCurrentPlayerNotificationRead({ notificationId }),
    onSuccess: invalidateNotifications,
  })
  const markAllReadMutation = useMutation({
    mutationFn: MeService.markAllCurrentPlayerNotificationsRead,
    onSuccess: invalidateNotifications,
  })

  const handleNotificationClick = (notification: PlayerNotificationPublic) => {
    if (!notification.read_at) {
      markReadMutation.mutate(notification.id)
    }
  }

  return (
    <div className="flex w-full max-w-5xl flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex flex-wrap items-baseline gap-2 text-2xl font-bold tracking-tight">
            {t("notifications.title")}
            <span className="text-muted-foreground text-sm font-medium">
              ({t("notifications.unreadCount", { count: unreadCount })})
            </span>
          </h1>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={unreadCount === 0 || markAllReadMutation.isPending}
          onClick={() => markAllReadMutation.mutate()}
        >
          {t("notifications.markAllRead")}
        </Button>
      </div>

      {notificationsQuery.isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-20 rounded-md" />
          ))}
        </div>
      ) : notificationsQuery.data?.data.length ? (
        <div className="overflow-hidden rounded-md border border-border bg-card">
          {notificationsQuery.data.data.map((notification) => {
            const display = buildNotificationDisplay(notification, t)
            const unread = !notification.read_at

            return (
              <div
                key={notification.id}
                data-testid="notification-row"
                className={cn(
                  "flex w-full items-start gap-3 border-border border-b bg-card px-4 py-4 text-left transition-colors last:border-b-0 hover:bg-accent/60",
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground",
                    unread && "border-primary/30 bg-primary/10 text-primary",
                  )}
                >
                  {display.icon}
                </span>
                <span className="min-w-0 flex-1 space-y-1.5">
                  <span className="flex items-start justify-between gap-3">
                    <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                      {display.showActor === false ? null : (
                        <NotificationActor actor={display.actor} />
                      )}
                      <NotificationAction
                        notification={notification}
                        display={display}
                        onMarkRead={() => {
                          handleNotificationClick(notification)
                        }}
                      />
                      {unread ? (
                        <Badge variant="secondary" className="text-[10px]">
                          {t("notifications.unread")}
                        </Badge>
                      ) : null}
                    </span>
                    <FormattedDateTime
                      value={notification.created_at}
                      display="contextual-relative"
                      className="shrink-0 whitespace-nowrap pt-1 text-muted-foreground text-xs"
                    />
                  </span>
                  {display.detail && notification.type !== "player_report" ? (
                    <span
                      className={cn(
                        "block text-muted-foreground text-sm",
                        notification.type === "map_review_comment_deleted" &&
                          "whitespace-pre-wrap",
                      )}
                    >
                      {display.detail}
                    </span>
                  ) : null}
                  {notification.type === "player_report" ? (
                    <ReportNotificationDetails
                      notification={notification}
                      onMarkRead={() => handleNotificationClick(notification)}
                    />
                  ) : null}
                </span>
              </div>
            )
          })}
          <TablePaginationFooter
            totalLabel={t("notifications.title")}
            totalCount={totalCount}
            pageIndex={pageIndex}
            pageCount={pageCount}
            pageSize={pageSize}
            onPageIndexChange={setPageIndex}
            onPageSizeChange={(nextPageSize) => {
              setPageSize(nextPageSize)
              setPageIndex(0)
            }}
            pageSizeOptions={NOTIFICATION_PAGE_SIZE_OPTIONS}
          />
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-border px-6 py-12 text-center text-muted-foreground text-sm">
          {t("notifications.empty")}
        </div>
      )}
    </div>
  )
}
