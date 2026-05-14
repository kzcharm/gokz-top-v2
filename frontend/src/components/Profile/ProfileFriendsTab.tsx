import { useTranslation } from "react-i18next"
import type { PlayerPublic } from "@/client"
import { PlayerDisplay } from "@/components/Common/PlayerDisplay"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"

import type { ProfileFriendSync } from "./profile-utils"

function FriendsListSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }, (_, index) => (
        <div
          key={index}
          className="rounded-2xl border border-border/70 bg-card/70 p-4"
        >
          <Skeleton className="h-12 w-full" />
        </div>
      ))}
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
    <div className="space-y-3" data-testid="profile-friends-list">
      {friends.map((friend) => (
        <div
          key={friend.steamid64}
          className="rounded-2xl border border-border/70 bg-card/70 p-4"
        >
          <PlayerDisplay player={friend} showSteamid />
        </div>
      ))}
    </div>
  )
}
