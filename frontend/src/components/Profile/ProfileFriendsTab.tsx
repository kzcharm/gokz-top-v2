import { useTranslation } from "react-i18next"
import type { PlayerPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"

import type { ProfileFriendSync } from "./profile-utils"

function FriendsListSkeleton() {
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {Array.from({ length: 4 }, (_, index) => (
        <div
          key={index}
          className="rounded-2xl border border-border/70 bg-card/70 p-4"
        >
          <Skeleton className="h-16 w-full" />
        </div>
      ))}
    </div>
  )
}

function FriendCard({ friend }: { friend: PlayerPublic }) {
  const { t } = useTranslation()

  return (
    <div
      className="rounded-2xl border border-border/70 bg-card/70 p-4"
      data-testid={`profile-friends-row-${friend.steamid64}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PlayerDisplay player={friend} className="min-w-0 flex-1" />
        <div className="min-w-[8rem] space-y-1 text-left lg:text-right">
          <p className="text-[11px] font-medium tracking-[0.08em] text-muted-foreground uppercase">
            {t("profile.summary.lastPlayed")}
          </p>
          {friend.last_played_at ? (
            <FormattedDateTime
              value={friend.last_played_at}
              display="relative"
              className="text-sm font-medium text-foreground"
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              {t("profile.unavailable")}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export function ProfileFriendsTab({
  friends,
  sync,
  loading,
  error,
}: {
  friends: PlayerPublic[]
  sync: ProfileFriendSync | null
  loading: boolean
  error: boolean
}) {
  const { t } = useTranslation()

  if (loading) {
    return <FriendsListSkeleton />
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t("profile.friends.loadFailedTitle")}</AlertTitle>
        <AlertDescription>
          {t("profile.friends.loadFailedBody")}
        </AlertDescription>
      </Alert>
    )
  }

  if (sync?.visibility === "private_profile") {
    return (
      <Alert data-testid="profile-friends-warning">
        <AlertTitle>{t("profile.friends.privateProfileTitle")}</AlertTitle>
        <AlertDescription>
          {t("profile.friends.privateProfileBody")}
        </AlertDescription>
      </Alert>
    )
  }

  if (sync?.visibility === "private_friends") {
    return (
      <Alert data-testid="profile-friends-warning">
        <AlertTitle>{t("profile.friends.privateFriendsTitle")}</AlertTitle>
        <AlertDescription>
          {t("profile.friends.privateFriendsBody")}
        </AlertDescription>
      </Alert>
    )
  }

  if (friends.length === 0) {
    return (
      <div
        className="rounded-2xl border border-dashed border-border/70 bg-muted/20 px-6 py-10 text-sm text-muted-foreground"
        data-testid="profile-friends-empty"
      >
        {t("profile.friends.empty")}
      </div>
    )
  }

  return (
    <div
      className="grid gap-3 lg:grid-cols-2"
      data-testid="profile-friends-list"
    >
      {friends.map((friend) => (
        <FriendCard key={friend.steamid64} friend={friend} />
      ))}
    </div>
  )
}
