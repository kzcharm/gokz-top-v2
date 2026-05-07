import { useQuery } from "@tanstack/react-query"
import { Radio, RefreshCw } from "lucide-react"
import { useState } from "react"

import { LiveService, type LiveStreamCardPublic, OpenAPI } from "@/client"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { getSocialPlatformLabel, SocialPlatformIcon } from "@/lib/social-links"
import { cn } from "@/lib/utils"

type StreamFilter = "live" | "offline"

function getOnlineValue(filter: StreamFilter): boolean {
  return filter === "live"
}

function resolvePreviewImageUrl(previewImageUrl: string | null | undefined) {
  if (!previewImageUrl) {
    return null
  }

  if (
    /^(?:[a-z]+:)?\/\//i.test(previewImageUrl) ||
    previewImageUrl.startsWith("data:")
  ) {
    return previewImageUrl
  }

  const configuredBase = OpenAPI.BASE || window.location.origin
  const baseUrl = new URL(configuredBase, window.location.origin)
  const normalizedPath =
    baseUrl.pathname === "/" ? "" : baseUrl.pathname.replace(/\/$/, "")
  const normalizedPreviewPath = previewImageUrl.startsWith("/")
    ? previewImageUrl
    : `/${previewImageUrl}`

  return `${baseUrl.origin}${normalizedPath}${normalizedPreviewPath}`
}

function getPlatformBadgeClass(
  platform: LiveStreamCardPublic["selected_platform"],
) {
  if (platform === "bilibili") {
    return "border-pink-300/25 bg-pink-500/90 text-white hover:bg-pink-500/90"
  }

  return "border-white/15 bg-white/10 text-white hover:bg-white/10"
}

function formatViewerCount(viewerCount: number) {
  return `${new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(viewerCount)} views`
}

function LiveCard({ stream }: { stream: LiveStreamCardPublic }) {
  const { formatDateTime } = useDateTimeFormat()
  const platformLabel = getSocialPlatformLabel(stream.selected_platform)
  const previewImageUrl = resolvePreviewImageUrl(stream.preview_image_url)
  const hoverPreviewImageUrl = resolvePreviewImageUrl(
    stream.hover_preview_image_url,
  )
  const timingLabel = stream.is_live
    ? stream.started_at
      ? `Started ${formatDateTime(stream.started_at, {
          display: "relative",
        })}`
      : "Live stream detected"
    : stream.last_streamed_at
      ? `Last streamed ${formatDateTime(stream.last_streamed_at, {
          display: "relative",
        })}`
      : "No stream history"

  return (
    <article className="overflow-hidden rounded-[24px] border border-border/80 bg-card shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg">
      <a
        href={stream.stream_url}
        target="_blank"
        rel="noopener noreferrer"
        className="group block"
      >
        <div className="relative aspect-video overflow-hidden bg-[linear-gradient(140deg,#0f172a_0%,#172554_45%,#1d4ed8_100%)]">
          {previewImageUrl ? (
            <img
              src={previewImageUrl}
              alt={`${stream.player.alias || stream.player.name} stream preview`}
              className={cn(
                "h-full w-full object-cover transition-all duration-300 group-hover:scale-[1.03]",
                hoverPreviewImageUrl ? "group-hover:opacity-0" : "",
              )}
              loading="lazy"
            />
          ) : null}
          {hoverPreviewImageUrl ? (
            <img
              src={hoverPreviewImageUrl}
              alt={`${stream.player.alias || stream.player.name} live keyframe preview`}
              className="absolute inset-0 h-full w-full object-cover opacity-0 transition-all duration-300 group-hover:scale-[1.03] group-hover:opacity-100"
              loading="lazy"
            />
          ) : null}
          <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(10,15,30,0.15)_0%,rgba(10,15,30,0.15)_35%,rgba(10,15,30,0.78)_100%)]" />
          <div className="absolute left-4 top-4">
            <Badge
              className={cn(
                "border-transparent text-white shadow-sm",
                stream.is_live
                  ? "bg-red-600 hover:bg-red-600"
                  : "bg-slate-900/80 hover:bg-slate-900/80",
              )}
            >
              {stream.is_live ? "Live" : "Offline"}
            </Badge>
          </div>
          {stream.last_viewer_count !== null &&
          stream.last_viewer_count !== undefined ? (
            <div className="absolute right-4 top-4">
              <Badge className="border-white/15 bg-black/45 text-white backdrop-blur-sm hover:bg-black/45">
                {formatViewerCount(stream.last_viewer_count)}
              </Badge>
            </div>
          ) : null}
          <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 p-4 text-white">
            <p className="line-clamp-2 flex-1 text-sm font-medium leading-5 text-white/95">
              {stream.stream_title ||
                `${stream.player.alias || stream.player.name} on ${platformLabel}`}
            </p>
            <div className="flex shrink-0 items-center gap-3 text-xs text-white/75">
              <Badge
                className={cn(
                  "backdrop-blur-sm",
                  getPlatformBadgeClass(stream.selected_platform),
                )}
              >
                <SocialPlatformIcon
                  platform={stream.selected_platform}
                  className="size-3.5"
                />
                {platformLabel}
              </Badge>
            </div>
          </div>
        </div>
      </a>
      <div className="space-y-3 p-4">
        <PlayerDisplay player={stream.player} className="min-w-0" />
        <p className="text-sm text-muted-foreground">{timingLabel}</p>
      </div>
    </article>
  )
}

function LiveCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-[24px] border border-border/80 bg-card">
      <Skeleton className="aspect-video w-full rounded-none" />
      <div className="space-y-3 p-4">
        <div className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-36" />
            <Skeleton className="h-3 w-24" />
          </div>
        </div>
        <Skeleton className="h-4 w-full" />
      </div>
    </div>
  )
}

function EmptyState({ filter }: { filter: StreamFilter }) {
  const message =
    filter === "live"
      ? "No verified Bilibili streams are live right now."
      : "No tracked players have streamed yet."

  return (
    <div className="rounded-[28px] border border-dashed border-border/80 bg-muted/20 px-6 py-16 text-center">
      <div className="mx-auto flex size-14 items-center justify-center rounded-full bg-background shadow-sm">
        <Radio className="size-6 text-muted-foreground" />
      </div>
      <h2 className="mt-5 text-xl font-semibold tracking-tight">
        Nothing to show
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
        {message}
      </p>
    </div>
  )
}

export function LivePage() {
  const [filter, setFilter] = useState<StreamFilter>("live")
  const isOnline = filter === "live"

  const streamsQuery = useQuery({
    queryKey: ["live-streams", filter],
    queryFn: () =>
      LiveService.readLiveStreams({
        online: getOnlineValue(filter),
      }),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Radio className="size-5 text-muted-foreground" />
          <h1 className="text-3xl font-semibold tracking-tight">Live</h1>
        </div>
        <button
          type="button"
          className={cn(
            "flex h-8 items-center gap-2 self-start rounded-md border px-2.5 shadow-xs transition-colors outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:self-auto",
            isOnline && "border-green-600/30 bg-green-600/5",
          )}
          onClick={() => {
            setFilter(isOnline ? "offline" : "live")
          }}
          title="Click to switch between online and offline streams"
        >
          <Switch
            aria-hidden="true"
            checked={isOnline}
            className="pointer-events-none"
            tabIndex={-1}
          />
          <span
            className={cn(
              "text-xs font-medium",
              isOnline && "text-green-700 dark:text-green-400",
            )}
          >
            Online
          </span>
        </button>
      </div>

      {streamsQuery.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Failed to load live streams</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>The live page could not be loaded from the API.</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => streamsQuery.refetch()}
            >
              <RefreshCw className="size-4" />
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {streamsQuery.isLoading ? (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 6 }).map((_, index) => (
            <LiveCardSkeleton key={index} />
          ))}
        </div>
      ) : streamsQuery.data && streamsQuery.data.data.length > 0 ? (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {streamsQuery.data.data.map((stream) => (
            <LiveCard
              key={`${stream.player.steamid64}-${stream.selected_platform}`}
              stream={stream}
            />
          ))}
        </div>
      ) : (
        <EmptyState filter={filter} />
      )}
    </section>
  )
}
