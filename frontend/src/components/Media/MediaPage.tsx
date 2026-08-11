import { useInfiniteQuery } from "@tanstack/react-query"
import { LoaderCircle, Play, RefreshCw, Video } from "lucide-react"

import { type MediaPostPublic, MediaService } from "@/client"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { getSocialPlatformLabel, SocialPlatformIcon } from "@/lib/social-links"
import { cn } from "@/lib/utils"

function formatDuration(value: number | null | undefined) {
  if (value === null || value === undefined) return null
  const minutes = Math.floor(value / 60)
  const seconds = value % 60
  return `${minutes}:${String(seconds).padStart(2, "0")}`
}

function formatViewCount(viewCount: number) {
  return `${new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(viewCount)} views`
}

function getPlatformBadgeClass(platform: MediaPostPublic["platform"]) {
  if (platform === "bilibili") {
    return "border-pink-300/25 bg-pink-500/90 text-white hover:bg-pink-500/90"
  }

  if (platform === "twitch") {
    return "border-violet-300/25 bg-violet-500/90 text-white hover:bg-violet-500/90"
  }

  if (platform === "youtube") {
    return "border-red-300/25 bg-red-600/90 text-white hover:bg-red-600/90"
  }

  return "border-white/15 bg-white/10 text-white hover:bg-white/10"
}

function MediaCard({ post }: { post: MediaPostPublic }) {
  const { formatDateTime } = useDateTimeFormat()
  const duration = formatDuration(post.duration_seconds)

  return (
    <article className="group overflow-hidden rounded-md border bg-card transition-shadow hover:shadow-md">
      <a
        href={post.url}
        target="_blank"
        rel="noopener noreferrer"
        className="block"
      >
        <div className="relative aspect-video overflow-hidden bg-muted">
          {post.thumbnail_url ? (
            <img
              src={post.thumbnail_url}
              alt=""
              className="size-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
              loading="lazy"
            />
          ) : (
            <div className="flex size-full items-center justify-center text-muted-foreground">
              <Video className="size-8" />
            </div>
          )}
          <div className="absolute inset-0 bg-black/0 transition-colors group-hover:bg-black/15" />
          <div className="absolute right-2 top-2">
            <Badge className="border-white/15 bg-black/45 text-white backdrop-blur-sm hover:bg-black/45">
              {formatViewCount(post.view_count)}
            </Badge>
          </div>
          {duration ? (
            <span className="absolute bottom-2 left-2 rounded bg-black/80 px-1.5 py-0.5 text-xs font-medium text-white">
              {duration}
            </span>
          ) : null}
          <div className="absolute bottom-2 right-2">
            <Badge
              className={cn(
                "backdrop-blur-sm",
                getPlatformBadgeClass(post.platform),
              )}
            >
              <SocialPlatformIcon platform={post.platform} className="size-3" />
              {getSocialPlatformLabel(post.platform)}
            </Badge>
          </div>
          <span className="absolute left-2 top-2 inline-flex size-7 items-center justify-center rounded-full bg-black/75 text-white opacity-0 transition-opacity group-hover:opacity-100">
            <Play className="size-3.5 fill-current" />
          </span>
        </div>
      </a>
      <div className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <a
            href={post.url}
            target="_blank"
            rel="noopener noreferrer"
            className="line-clamp-2 flex-1 text-sm font-semibold leading-5 hover:underline"
          >
            {post.title}
          </a>
          <span className="mt-0.5 shrink-0 text-xs font-normal text-muted-foreground">
            {formatDateTime(post.published_at, { display: "relative" })}
          </span>
        </div>
        <PlayerDisplay player={post.player} className="min-w-0" />
      </div>
    </article>
  )
}

function MediaCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-md border">
      <Skeleton className="aspect-video w-full rounded-none" />
      <div className="space-y-2 p-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  )
}

export function MediaPage() {
  const postsQuery = useInfiniteQuery({
    queryKey: ["media-posts"],
    queryFn: ({ pageParam }) =>
      MediaService.readMediaPosts({ cursor: pageParam, limit: 24 }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
  const posts = postsQuery.data?.pages.flatMap((page) => page.data) ?? []

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3">
        <Video className="size-5 text-muted-foreground" />
        <h1 className="text-3xl font-semibold">Media</h1>
      </div>
      {postsQuery.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Failed to load media</AlertTitle>
          <AlertDescription className="flex items-center gap-3">
            <span>The media feed could not be loaded from the API.</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => postsQuery.refetch()}
            >
              <RefreshCw className="size-4" />
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {postsQuery.isLoading ? (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <MediaCardSkeleton key={index} />
          ))}
        </div>
      ) : posts.length ? (
        <>
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {posts.map((post) => (
              <MediaCard key={post.id} post={post} />
            ))}
          </div>
          {postsQuery.hasNextPage ? (
            <div className="flex justify-center">
              <Button
                variant="outline"
                onClick={() => postsQuery.fetchNextPage()}
                disabled={postsQuery.isFetchingNextPage}
              >
                {postsQuery.isFetchingNextPage ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : null}
                Load more
              </Button>
            </div>
          ) : null}
        </>
      ) : (
        <div className="border border-dashed px-6 py-16 text-center text-muted-foreground">
          <Video className="mx-auto mb-3 size-8" />
          <p>No recent videos from verified players yet.</p>
        </div>
      )}
    </section>
  )
}
