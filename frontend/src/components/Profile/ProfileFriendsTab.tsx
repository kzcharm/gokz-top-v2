import { useQuery } from "@tanstack/react-query"
import { ArrowDown, ArrowUp } from "lucide-react"
import { type ReactNode, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import type { PlayerPublic } from "@/client"
import { getCountryName } from "@/components/Common/CountryFlag"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import {
  getPlayerDisplayName,
  PlayerDisplay,
} from "@/components/Common/PlayerDisplay"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"
import { compareLocaleText } from "@/i18n/locale"
import { fetchPlayersForDisplay } from "@/lib/player-graphql"

import type { ProfileFriendSync } from "./profile-utils"

type FriendSortField =
  | "name"
  | "steamid64"
  | "country"
  | "rating"
  | "last_played"
type FriendSortDirection = "asc" | "desc"

function FriendSortControl({
  active,
  direction,
  label,
  onClick,
  testId,
}: {
  active: boolean
  direction: FriendSortDirection
  label: string
  onClick: () => void
  testId: string
}) {
  return (
    <button
      type="button"
      className="-mx-2 -my-1 flex items-center gap-2 rounded-md px-2 py-1 text-left hover:bg-accent"
      data-testid={testId}
      onClick={onClick}
    >
      <span className="text-sm font-medium">{label}</span>
      {active ? (
        direction === "asc" ? (
          <ArrowUp className="h-3 w-3" />
        ) : (
          <ArrowDown className="h-3 w-3" />
        )
      ) : null}
    </button>
  )
}

function FriendsListSkeleton() {
  return (
    <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
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
      <div className="flex items-center justify-between gap-3">
        <PlayerDisplay player={friend} className="min-w-0 flex-1" />
        <div className="min-w-fit text-right">
          {friend.last_played_at ? (
            <FormattedDateTime
              value={friend.last_played_at}
              display="relative"
              className="text-sm font-medium whitespace-nowrap text-muted-foreground"
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
  actions,
}: {
  friends: PlayerPublic[]
  sync: ProfileFriendSync | null
  loading: boolean
  error: boolean
  actions?: ReactNode
}) {
  const { t, i18n } = useTranslation()
  const [sortField, setSortField] = useState<FriendSortField>("last_played")
  const [sortDirection, setSortDirection] =
    useState<FriendSortDirection>("desc")
  const friendSteamid64s = useMemo(
    () => friends.map((friend) => friend.steamid64),
    [friends],
  )
  const friendDisplayPlayersQuery = useQuery({
    queryKey: ["profile-friends-display-players", ...friendSteamid64s],
    enabled: friendSteamid64s.length > 0,
    queryFn: () => fetchPlayersForDisplay(friendSteamid64s),
    staleTime: 60_000,
  })
  const hydratedRatingsBySteamid64 = useMemo(
    () =>
      new Map(
        (friendDisplayPlayersQuery.data ?? [])
          .filter((player) => player !== null)
          .map((player) => [player.steamid64, player.rating]),
      ),
    [friendDisplayPlayersQuery.data],
  )

  const handleSortChange = (nextSortField: FriendSortField) => {
    setSortField(nextSortField)
    setSortDirection((currentDirection) =>
      sortField === nextSortField
        ? currentDirection === "asc"
          ? "desc"
          : "asc"
        : nextSortField === "last_played" || nextSortField === "rating"
          ? "desc"
          : "asc",
    )
  }

  const sortedFriends = useMemo(() => {
    const directionMultiplier = sortDirection === "asc" ? 1 : -1

    const compareNullableNumber = (
      left: number | null,
      right: number | null,
    ): number => {
      if (left === null && right === null) {
        return 0
      }
      if (left === null) {
        return 1
      }
      if (right === null) {
        return -1
      }
      return left - right
    }

    return [...friends].sort((left, right) => {
      let comparison = 0

      if (sortField === "steamid64") {
        comparison = left.steamid64.localeCompare(right.steamid64)
      } else if (sortField === "country") {
        comparison = compareLocaleText(
          getCountryName(left.country, i18n.resolvedLanguage) ?? "",
          getCountryName(right.country, i18n.resolvedLanguage) ?? "",
          { sensitivity: "base" },
          i18n.resolvedLanguage,
        )
      } else if (sortField === "rating") {
        comparison = compareNullableNumber(
          hydratedRatingsBySteamid64.get(left.steamid64) ?? null,
          hydratedRatingsBySteamid64.get(right.steamid64) ?? null,
        )
      } else if (sortField === "last_played") {
        comparison = compareNullableNumber(
          left.last_played_at ? new Date(left.last_played_at).getTime() : null,
          right.last_played_at ? new Date(right.last_played_at).getTime() : null,
        )
      } else {
        comparison = compareLocaleText(
          getPlayerDisplayName(left),
          getPlayerDisplayName(right),
          { sensitivity: "base" },
          i18n.resolvedLanguage,
        )
      }

      if (comparison !== 0) {
        return comparison * directionMultiplier
      }

      return left.steamid64.localeCompare(right.steamid64) * directionMultiplier
    })
  }, [
    friends,
    hydratedRatingsBySteamid64,
    i18n.resolvedLanguage,
    sortDirection,
    sortField,
  ])

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
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div
          className="rounded-[20px] border border-border/70 bg-muted/95 px-6 py-3 shadow-sm"
          data-testid="profile-friends-sort-bar"
        >
          <div className="flex flex-wrap gap-4">
            <FriendSortControl
              active={sortField === "name"}
              direction={sortDirection}
              label={t("profile.friends.sortFields.name")}
              testId="profile-friends-sort-name"
              onClick={() => handleSortChange("name")}
            />
            <FriendSortControl
              active={sortField === "steamid64"}
              direction={sortDirection}
              label={t("profile.friends.sortFields.steamid64")}
              testId="profile-friends-sort-steamid64"
              onClick={() => handleSortChange("steamid64")}
            />
            <FriendSortControl
              active={sortField === "country"}
              direction={sortDirection}
              label={t("profile.friends.sortFields.country")}
              testId="profile-friends-sort-country"
              onClick={() => handleSortChange("country")}
            />
            <FriendSortControl
              active={sortField === "rating"}
              direction={sortDirection}
              label={t("profile.friends.sortFields.rating")}
              testId="profile-friends-sort-rating"
              onClick={() => handleSortChange("rating")}
            />
            <FriendSortControl
              active={sortField === "last_played"}
              direction={sortDirection}
              label={t("profile.friends.sortFields.lastPlayed")}
              testId="profile-friends-sort-last-played"
              onClick={() => handleSortChange("last_played")}
            />
          </div>
        </div>

        {actions ? <div className="flex justify-start sm:justify-end">{actions}</div> : null}
      </div>

      <div
        className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3"
        data-testid="profile-friends-list"
      >
        {sortedFriends.map((friend) => (
          <FriendCard key={friend.steamid64} friend={friend} />
        ))}
      </div>
    </div>
  )
}
