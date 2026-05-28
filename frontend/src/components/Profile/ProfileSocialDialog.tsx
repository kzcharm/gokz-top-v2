import { useInfiniteQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import type { PlayerPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

import {
  fetchProfileFollowers,
  fetchProfileFollowing,
  fetchProfileLikers,
  formatNumber,
  type ProfileLikerPublic,
} from "./profile-utils"

export type ProfileSocialTab = "likes" | "followers" | "following"

type SocialPage = {
  data: Array<PlayerPublic | ProfileLikerPublic>
  count: number
}

function isProfileLiker(
  player: PlayerPublic | ProfileLikerPublic,
): player is ProfileLikerPublic {
  return "latest_like_at" in player
}

function SocialList({
  active,
  emptyLabel,
  hasMore,
  isError,
  isFetchingNextPage,
  isLoading,
  players,
  showLikeTimestamps = false,
  onLoadMore,
}: {
  active: boolean
  emptyLabel: string
  hasMore: boolean
  isError: boolean
  isFetchingNextPage: boolean
  isLoading: boolean
  players: Array<PlayerPublic | ProfileLikerPublic>
  showLikeTimestamps?: boolean
  onLoadMore: () => void
}) {
  const { t } = useTranslation()
  if (!active) {
    return null
  }

  if (isLoading) {
    return (
      <div className="space-y-3 py-2">
        {Array.from({ length: 3 }, (_, index) => (
          <div
            key={index}
            className="h-16 animate-pulse rounded-2xl border border-border/60 bg-muted/50"
          />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="rounded-2xl border border-dashed border-destructive/40 bg-destructive/5 px-4 py-6 text-sm text-muted-foreground">
        {t("profile.socialDialog.loadFailed")}
      </div>
    )
  }

  if (players.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/70 bg-muted/20 px-4 py-6 text-sm text-muted-foreground">
        {emptyLabel}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {players.map((player) => (
          <div
            key={player.steamid64}
            className="flex items-center justify-between gap-3 rounded-2xl border border-border/70 bg-card/70 p-3"
            data-testid={`profile-social-row-${player.steamid64}`}
          >
            <div className="min-w-0">
              <PlayerDisplay player={player} showSteamid />
            </div>
            {showLikeTimestamps &&
            isProfileLiker(player) &&
            player.latest_like_at ? (
              <div className="shrink-0 text-right text-xs text-muted-foreground">
                <FormattedDateTime
                  value={player.latest_like_at}
                  display="relative"
                  tickerMs={60_000}
                />
              </div>
            ) : null}
          </div>
        ))}
      </div>

      {hasMore ? (
        <Button
          type="button"
          variant="outline"
          className="w-full"
          onClick={onLoadMore}
          disabled={isFetchingNextPage}
        >
          {isFetchingNextPage
            ? t("common.loading")
            : t("profile.socialDialog.loadMore")}
        </Button>
      ) : null}
    </div>
  )
}

function useSocialList({
  enabled,
  identifier,
  kind,
}: {
  enabled: boolean
  identifier: string
  kind: ProfileSocialTab
}) {
  return useInfiniteQuery({
    queryKey: ["profile-social", kind, identifier],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      kind === "likes"
        ? fetchProfileLikers({ identifier, offset: pageParam })
        : kind === "followers"
          ? fetchProfileFollowers({ identifier, offset: pageParam })
          : fetchProfileFollowing({ identifier, offset: pageParam }),
    getNextPageParam: (lastPage: SocialPage, allPages: SocialPage[]) => {
      const loadedCount = allPages.reduce(
        (total, page) => total + page.data.length,
        0,
      )
      return loadedCount < lastPage.count ? loadedCount : undefined
    },
    enabled,
    staleTime: 30_000,
  })
}

export function ProfileSocialDialog({
  followerCount,
  followingCount,
  identifier,
  likeCount,
  onOpenChange,
  open,
  tab,
  onTabChange,
}: {
  followerCount: number
  followingCount: number
  identifier: string
  likeCount: number
  onOpenChange: (open: boolean) => void
  open: boolean
  tab: ProfileSocialTab
  onTabChange: (tab: ProfileSocialTab) => void
}) {
  const { t } = useTranslation()
  const likesQuery = useSocialList({
    enabled: open && tab === "likes",
    identifier,
    kind: "likes",
  })
  const followersQuery = useSocialList({
    enabled: open && tab === "followers",
    identifier,
    kind: "followers",
  })
  const followingQuery = useSocialList({
    enabled: open && tab === "following",
    identifier,
    kind: "following",
  })

  const likePages = likesQuery.data?.pages ?? []
  const followerPages = followersQuery.data?.pages ?? []
  const followingPages = followingQuery.data?.pages ?? []
  const likers = likePages.flatMap((page) => page.data)
  const followers = followerPages.flatMap((page) => page.data)
  const following = followingPages.flatMap((page) => page.data)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[85vh] overflow-y-auto sm:max-w-2xl"
        data-testid="profile-social-dialog"
      >
        <DialogHeader>
          <DialogTitle>{t("profile.socialDialog.title")}</DialogTitle>
        </DialogHeader>

        <Tabs
          value={tab}
          onValueChange={(value) => onTabChange(value as ProfileSocialTab)}
          className="gap-4"
        >
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="likes">
              {t("profile.socialDialog.likesTab", {
                count: formatNumber(likeCount),
              })}
            </TabsTrigger>
            <TabsTrigger value="followers">
              {t("profile.socialDialog.followersTab", {
                count: formatNumber(followerCount),
              })}
            </TabsTrigger>
            <TabsTrigger value="following">
              {t("profile.socialDialog.followingTab", {
                count: formatNumber(followingCount),
              })}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="likes" className="space-y-4">
            <SocialList
              active={tab === "likes"}
              emptyLabel={t("profile.socialDialog.emptyLikes")}
              hasMore={likesQuery.hasNextPage ?? false}
              isError={likesQuery.isError}
              isFetchingNextPage={likesQuery.isFetchingNextPage}
              isLoading={likesQuery.isLoading}
              players={likers}
              showLikeTimestamps
              onLoadMore={() => {
                void likesQuery.fetchNextPage()
              }}
            />
          </TabsContent>

          <TabsContent value="followers" className="space-y-4">
            <SocialList
              active={tab === "followers"}
              emptyLabel={t("profile.socialDialog.emptyFollowers")}
              hasMore={followersQuery.hasNextPage ?? false}
              isError={followersQuery.isError}
              isFetchingNextPage={followersQuery.isFetchingNextPage}
              isLoading={followersQuery.isLoading}
              players={followers}
              onLoadMore={() => {
                void followersQuery.fetchNextPage()
              }}
            />
          </TabsContent>

          <TabsContent value="following" className="space-y-4">
            <SocialList
              active={tab === "following"}
              emptyLabel={t("profile.socialDialog.emptyFollowing")}
              hasMore={followingQuery.hasNextPage ?? false}
              isError={followingQuery.isError}
              isFetchingNextPage={followingQuery.isFetchingNextPage}
              isLoading={followingQuery.isLoading}
              players={following}
              onLoadMore={() => {
                void followingQuery.fetchNextPage()
              }}
            />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
