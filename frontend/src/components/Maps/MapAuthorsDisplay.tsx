import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import {
  getPlayerDisplayName,
  PlayerDisplay,
} from "@/components/Common/PlayerDisplay"
import {
  Avatar,
  AvatarFallback,
  AvatarGroup,
  AvatarGroupCount,
  AvatarImage,
} from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import {
  fetchPlayersForDisplay,
  type GraphqlPlayer,
} from "@/lib/player-graphql"
import { cn } from "@/lib/utils"
import { getInitials } from "@/utils"

type MapAuthorsDisplayProps = {
  authors?: string[] | null
  noSteamidNames?: string[] | null
  className?: string
  playerClassName?: string
  emptyClassName?: string
  compact?: boolean
  variant?: "default" | "avatar-group"
}

function normalizeList(values?: string[] | null) {
  return Array.from(
    new Set((values ?? []).map((value) => value.trim()).filter(Boolean)),
  )
}

export function MapAuthorsDisplay({
  authors,
  noSteamidNames,
  className,
  playerClassName,
  emptyClassName,
  compact = false,
  variant = "default",
}: MapAuthorsDisplayProps) {
  const { t } = useTranslation()
  const steamidAuthors = normalizeList(authors)
  const nameOnlyAuthors = normalizeList(noSteamidNames)
  const playerQuery = useQuery({
    queryKey: ["map-author-display", steamidAuthors],
    enabled: variant === "avatar-group" && steamidAuthors.length > 0,
    queryFn: () => fetchPlayersForDisplay(steamidAuthors),
    staleTime: 60_000,
  })

  if (steamidAuthors.length === 0 && nameOnlyAuthors.length === 0) {
    return (
      <span className={cn("text-sm text-muted-foreground", emptyClassName)}>
        {t("maps.unknownAuthor")}
      </span>
    )
  }

  if (variant === "avatar-group") {
    return (
      <MapAuthorsAvatarGroup
        steamidAuthors={steamidAuthors}
        players={playerQuery.data ?? []}
        nameOnlyAuthors={nameOnlyAuthors}
        className={className}
      />
    )
  }

  return (
    <div className={cn("flex min-w-0 flex-wrap items-center gap-2", className)}>
      {steamidAuthors.map((steamid64) => (
        <PlayerDisplay
          key={steamid64}
          player={{ steamid64 }}
          className={cn(
            compact ? "max-w-[11rem]" : "max-w-[15rem]",
            playerClassName,
          )}
          nameMaxLength={compact ? 18 : 24}
          showCountryFlag={!compact}
          hideAvatarWithoutSteamid64
        />
      ))}
      {nameOnlyAuthors.map((name) => (
        <Badge
          key={name}
          variant="secondary"
          className="max-w-full truncate font-medium"
          title={name}
        >
          {name}
        </Badge>
      ))}
    </div>
  )
}

function getAvatarHash(player: GraphqlPlayer | null | undefined) {
  return player?.avatarHash ?? null
}

function MapAuthorsAvatarGroup({
  steamidAuthors,
  players,
  nameOnlyAuthors,
  className,
}: {
  steamidAuthors: string[]
  players: Array<GraphqlPlayer | null>
  nameOnlyAuthors: string[]
  className?: string
}) {
  const steamidEntries = steamidAuthors.map((steamid64, index) => {
    const player = players[index] ?? null
    const label = getPlayerDisplayName(player, steamid64)
    const avatarHash = getAvatarHash(player)
    return {
      key: steamid64,
      steamid64,
      label,
      avatarSrc: avatarHash
        ? `https://avatars.steamstatic.com/${avatarHash}_full.jpg`
        : null,
    }
  })
  const nameOnlyEntries = nameOnlyAuthors.map((name) => ({
    key: `name:${name}`,
    steamid64: null,
    label: name,
    avatarSrc: null,
  }))
  const entries = [...steamidEntries, ...nameOnlyEntries]
  const visibleEntries = entries.slice(0, 3)
  const overflowCount = Math.max(entries.length - visibleEntries.length, 0)
  const linkedEntries = entries.filter((entry) => entry.steamid64 !== null)
  const unlinkedEntries = entries.filter((entry) => entry.steamid64 === null)

  return (
    <div className={cn("flex min-w-0 items-center gap-2", className)}>
      <span className="shrink-0 text-sm text-muted-foreground">by</span>
      <AvatarGroup className="shrink-0">
        {visibleEntries.map((entry) => (
          <AuthorAvatar key={entry.key} entry={entry} />
        ))}
        {overflowCount > 0 ? (
          <AvatarGroupCount className="size-7 text-[10px]">
            +{overflowCount}
          </AvatarGroupCount>
        ) : null}
      </AvatarGroup>
      <span
        className="min-w-0 truncate text-sm text-muted-foreground"
        title={entries.map((entry) => entry.label).join(", ")}
      >
        {linkedEntries.map((entry, index) => (
          <span key={entry.key}>
            {index > 0 ? ", " : null}
            <Link
              to="/profile/$identifier"
              params={{ identifier: entry.steamid64 ?? "" }}
              className="font-medium text-foreground underline-offset-4 transition-colors hover:text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {entry.label}
            </Link>
          </span>
        ))}
        {unlinkedEntries.map((entry, index) => (
          <span key={entry.key}>
            {linkedEntries.length > 0 || index > 0 ? ", " : null}
            {entry.label}
          </span>
        ))}
      </span>
    </div>
  )
}

type AvatarGroupEntry = {
  avatarSrc: string | null
  key: string
  label: string
  steamid64: string | null
}

function AuthorAvatar({ entry }: { entry: AvatarGroupEntry }) {
  const highlightClassName =
    "relative z-0 transition-transform duration-150 hover:z-10 hover:scale-110 focus-visible:z-10"
  const avatar = (
    <Avatar
      className={cn(
        "border-background size-7 border-2",
        entry.steamid64 === null ? highlightClassName : null,
      )}
      title={entry.label}
    >
      {entry.avatarSrc ? (
        <AvatarImage src={entry.avatarSrc} alt={`${entry.label} avatar`} />
      ) : null}
      <AvatarFallback className="bg-zinc-600 text-[10px] font-semibold text-white">
        {getInitials(entry.label || "?").slice(0, 2) || "?"}
      </AvatarFallback>
    </Avatar>
  )

  if (entry.steamid64 === null) {
    return avatar
  }

  return (
    <Link
      to="/profile/$identifier"
      params={{ identifier: entry.steamid64 }}
      aria-label={`Open ${entry.label}`}
      className={cn(
        "block rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        highlightClassName,
      )}
    >
      {avatar}
    </Link>
  )
}
