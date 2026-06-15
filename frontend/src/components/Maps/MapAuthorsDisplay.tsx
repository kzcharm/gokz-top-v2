import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
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
  expandable?: boolean
  showByPrefix?: boolean
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
  expandable = false,
  showByPrefix = true,
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
        expandable={expandable}
        showByPrefix={showByPrefix}
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

const AUTHOR_AVATAR_SIZE_PX = 28
const AUTHOR_AVATAR_STACK_STEP_PX = 14
const AUTHOR_ROW_GAP_PX = 8

function getStackedAvatarWidth(visibleCount: number, totalCount: number) {
  const childCount = visibleCount + (visibleCount < totalCount ? 1 : 0)

  if (childCount <= 0) {
    return 0
  }

  return AUTHOR_AVATAR_SIZE_PX + (childCount - 1) * AUTHOR_AVATAR_STACK_STEP_PX
}

function measureAuthorTextWidth(
  context: CanvasRenderingContext2D,
  labels: string[],
  count: number,
) {
  return context.measureText(labels.slice(0, count).join(", ")).width
}

function getDynamicCollapsedLimit({
  availableWidth,
  context,
  labels,
  showByPrefix,
}: {
  availableWidth: number
  context: CanvasRenderingContext2D
  labels: string[]
  showByPrefix: boolean
}) {
  if (labels.length <= 3 || availableWidth <= 0) {
    return labels.length
  }

  const prefixWidth = showByPrefix ? context.measureText("by").width : 0
  const rootGapWidth = (showByPrefix ? 2 : 1) * AUTHOR_ROW_GAP_PX

  for (let count = labels.length; count >= 1; count -= 1) {
    const rowWidth =
      prefixWidth +
      rootGapWidth +
      getStackedAvatarWidth(count, labels.length) +
      measureAuthorTextWidth(context, labels, count)

    if (rowWidth <= availableWidth) {
      return count
    }
  }

  return 1
}

function MapAuthorsAvatarGroup({
  steamidAuthors,
  players,
  nameOnlyAuthors,
  className,
  expandable,
  showByPrefix,
}: {
  steamidAuthors: string[]
  players: Array<GraphqlPlayer | null>
  nameOnlyAuthors: string[]
  className?: string
  expandable: boolean
  showByPrefix: boolean
}) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [collapsedLimit, setCollapsedLimit] = useState(3)
  const containerRef = useRef<HTMLDivElement>(null)
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
  const entryLabelsKey = entries.map((entry) => entry.label).join("\u0000")
  const visibleLimit = expandable
    ? Math.min(collapsedLimit, entries.length)
    : Math.min(3, entries.length)
  const visibleEntries = isExpanded ? entries : entries.slice(0, visibleLimit)
  const overflowCount = Math.max(entries.length - visibleEntries.length, 0)
  const textEntries = expandable && !isExpanded ? visibleEntries : entries
  const canCollapse = expandable && entries.length > visibleLimit
  const linkedEntries = textEntries.filter((entry) => entry.steamid64 !== null)
  const unlinkedEntries = textEntries.filter(
    (entry) => entry.steamid64 === null,
  )

  useEffect(() => {
    const entryLabels =
      entryLabelsKey.length > 0 ? entryLabelsKey.split("\u0000") : []

    if (!expandable || entryLabels.length === 0) {
      setCollapsedLimit(Math.min(3, entryLabels.length))
      return
    }

    const container = containerRef.current
    const parent = container?.parentElement
    const canvas = document.createElement("canvas")
    const context = canvas.getContext("2d")

    if (!container || !context) {
      setCollapsedLimit(Math.min(3, entryLabels.length))
      return
    }

    const updateLimit = () => {
      const style = window.getComputedStyle(container)
      context.font = [
        style.fontStyle,
        style.fontVariant,
        "500",
        style.fontSize,
        style.fontFamily,
      ].join(" ")

      const availableWidth = parent?.clientWidth ?? container.clientWidth
      const nextLimit = getDynamicCollapsedLimit({
        availableWidth,
        context,
        labels: entryLabels,
        showByPrefix,
      })

      setCollapsedLimit((currentLimit) =>
        currentLimit === nextLimit ? currentLimit : nextLimit,
      )
    }

    updateLimit()

    const observer = new ResizeObserver(updateLimit)
    observer.observe(parent ?? container)

    return () => observer.disconnect()
  }, [entryLabelsKey, expandable, showByPrefix])

  if (expandable && isExpanded) {
    return (
      <div
        ref={containerRef}
        className={cn("flex min-w-0 flex-wrap items-center gap-2", className)}
      >
        {showByPrefix ? (
          <span className="shrink-0 text-sm text-muted-foreground">by</span>
        ) : null}
        {entries.map((entry) => (
          <AuthorIdentity key={entry.key} entry={entry} />
        ))}
        {canCollapse ? (
          <AvatarGroupCount asChild className="size-7 text-[10px]">
            <button
              type="button"
              aria-expanded={isExpanded}
              aria-label="Collapse authors"
              onClick={() => setIsExpanded(false)}
            >
              -
            </button>
          </AvatarGroupCount>
        ) : null}
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className={cn("flex min-w-0 items-center gap-2", className)}
    >
      {showByPrefix ? (
        <span className="shrink-0 text-sm text-muted-foreground">by</span>
      ) : null}
      <AvatarGroup className="shrink-0">
        {visibleEntries.map((entry) => (
          <AuthorAvatar key={entry.key} entry={entry} />
        ))}
        {overflowCount > 0 && expandable ? (
          <AvatarGroupCount asChild className="size-7 text-[10px]">
            <button
              type="button"
              aria-expanded={isExpanded}
              aria-label={`Show ${overflowCount} more authors`}
              onClick={() => setIsExpanded(true)}
            >
              +{overflowCount}
            </button>
          </AvatarGroupCount>
        ) : overflowCount > 0 ? (
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

function AuthorAvatarImage({ entry }: { entry: AvatarGroupEntry }) {
  return (
    <Avatar className="border-background size-7 border-2" title={entry.label}>
      {entry.avatarSrc ? (
        <AvatarImage src={entry.avatarSrc} alt={`${entry.label} avatar`} />
      ) : null}
      <AvatarFallback className="bg-zinc-600 text-[10px] font-semibold text-white">
        {getInitials(entry.label || "?").slice(0, 2) || "?"}
      </AvatarFallback>
    </Avatar>
  )
}

function AuthorAvatar({ entry }: { entry: AvatarGroupEntry }) {
  if (entry.steamid64 === null) {
    return (
      <span className="relative z-0 transition-transform duration-150 hover:z-20 hover:scale-110">
        <AuthorAvatarImage entry={entry} />
      </span>
    )
  }

  return (
    <Link
      to="/profile/$identifier"
      params={{ identifier: entry.steamid64 }}
      aria-label={`Open ${entry.label}`}
      className={cn(
        "block rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        "relative z-0 transition-transform duration-150 hover:z-20 hover:scale-110 focus-visible:z-20",
      )}
    >
      <AuthorAvatarImage entry={entry} />
    </Link>
  )
}

function AuthorIdentity({ entry }: { entry: AvatarGroupEntry }) {
  const content = (
    <>
      <AuthorAvatarImage entry={entry} />
      <span className="max-w-[12rem] truncate text-sm font-medium">
        {entry.label}
      </span>
    </>
  )

  if (entry.steamid64 === null) {
    return (
      <span className="inline-flex min-w-0 items-center gap-1.5 text-muted-foreground">
        {content}
      </span>
    )
  }

  return (
    <Link
      to="/profile/$identifier"
      params={{ identifier: entry.steamid64 }}
      className="inline-flex min-w-0 items-center gap-1.5 rounded-full text-foreground underline-offset-4 transition-colors hover:text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      {content}
    </Link>
  )
}
