import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "@tanstack/react-router"
import * as Flags from "country-flag-icons/react/3x2"
import {
  Copy,
  ExternalLink,
  IdCard,
  UserCheck,
  UserPlus,
  UserRound,
} from "lucide-react"
import type {
  ComponentType,
  KeyboardEvent,
  MouseEvent,
  ReactNode,
  SVGProps,
} from "react"
import { useEffect, useState } from "react"
import noneFlagSrc from "@/assets/flags/none.svg"
import playerAvatarPlaceholderSrc from "@/assets/player-avatar-placeholder.jpg"
import {
  ApiError,
  MapsService,
  PlayersService,
  type RecordScope,
  type RecordType,
} from "@/client"
import EditPlayer from "@/components/AdminPlayers/EditPlayer"
import { formatRecordTime } from "@/components/Records/utils"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import useCustomToast from "@/hooks/useCustomToast"
import { getSteamid64FromAccessToken } from "@/lib/auth"
import { loadPlayerForDisplay } from "@/lib/player-graphql"
import { cn, truncateText } from "@/lib/utils"
import { getInitials } from "@/utils"

const countryNameFormatter =
  typeof Intl !== "undefined" && "DisplayNames" in Intl
    ? new Intl.DisplayNames(["en"], { type: "region" })
    : null

const flagComponents = Flags as Record<
  string,
  ComponentType<SVGProps<SVGSVGElement>>
>
const steamid64Pattern = /^\d{17}$/

export type PlayerDisplayPlayer = {
  steamid64: string
  displayName?: string | null
  name?: string | null
  alias?: string | null
  customId?: string | null
  avatarHash?: string | null
  avatar_hash?: string | null
  country?: string | null
  isWebsiteUser?: boolean
  is_website_user?: boolean
  lastPlayedAt?: string | null
  last_played_at?: string | null
}

type PlayerDisplaySubline =
  | {
      type: "steamid64"
    }
  | {
      type: "text"
      value?: string | null
    }
  | {
      type: "wr"
      mapId?: number | null
      mapName?: string | null
      scope?: RecordScope
      recordType?: RecordType
      emptyLabel?: string | null
    }

interface PlayerDisplayProps {
  player?: PlayerDisplayPlayer | null
  fallbackSteamid64?: string
  showSteamid?: boolean
  showCountryFlag?: boolean
  subline?: PlayerDisplaySubline | null
  className?: string
  nameMaxLength?: number
  disableProfileLink?: boolean
}

type PlayerContextMenuItemsProps = {
  children?: ReactNode
  displayName: string
  hasProfileLink: boolean
  player?: {
    alias?: string | null
    country?: string | null
    name: string
    steamid64: string
  }
  steamProfileUrl: string | null
  steamid64: string
}

function hasWebsiteUserAvatarRing(
  player: PlayerDisplayProps["player"],
): boolean {
  return player?.isWebsiteUser === true || player?.is_website_user === true
}

export function getPlayerDisplayName(
  player?: PlayerDisplayPlayer | null,
  fallbackSteamid64?: string,
): string {
  const displayName = player?.displayName?.trim()
  if (displayName) {
    return displayName
  }

  const alias = player?.alias?.trim()
  if (alias) {
    return alias
  }

  const name = player?.name?.trim()
  if (name) {
    return name
  }

  return fallbackSteamid64 || "N/A"
}

function getPlayerAvatarHash(
  player?: PlayerDisplayPlayer | null,
): string | null {
  return player?.avatarHash ?? player?.avatar_hash ?? null
}

function shouldHydratePlayer(player?: PlayerDisplayPlayer | null): boolean {
  if (!player) {
    return true
  }

  const hasDisplayName =
    Boolean(player.displayName?.trim()) ||
    Boolean(player.alias?.trim()) ||
    Boolean(player.name?.trim())
  const hasCountry = Boolean(player.country?.trim())
  const hasAvatarHash = Boolean(getPlayerAvatarHash(player))
  const hasWebsiteUserState =
    player.isWebsiteUser !== undefined || player.is_website_user !== undefined

  return (
    !hasDisplayName || !hasCountry || !hasAvatarHash || !hasWebsiteUserState
  )
}

export function PlayerContextMenuItems({
  children,
  displayName,
  hasProfileLink,
  player,
  steamProfileUrl,
  steamid64,
}: PlayerContextMenuItemsProps) {
  const navigate = useNavigate()
  const [, copyToClipboard] = useCopyToClipboard()

  const handleGotoProfile = () => {
    if (!hasProfileLink) {
      return
    }

    void navigate({
      to: "/profile/$identifier",
      params: { identifier: steamid64 },
    })
  }

  const handleOpenSteamProfile = () => {
    if (!steamProfileUrl) {
      return
    }

    window.open(steamProfileUrl, "_blank", "noopener,noreferrer")
  }

  const handleCopySteamid64 = () => {
    if (!hasProfileLink) {
      return
    }

    void copyToClipboard(steamid64)
  }

  const handleCopyName = () => {
    void copyToClipboard(displayName)
  }

  return (
    <>
      <DropdownMenuItem onSelect={handleGotoProfile}>
        <UserRound />
        Goto Profile
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={handleOpenSteamProfile}>
        <ExternalLink />
        Steam Profile
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={handleCopySteamid64}>
        <Copy />
        Copy SteamID64
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={handleCopyName}>
        <IdCard />
        Copy Name
      </DropdownMenuItem>
      {player ? <EditPlayer player={player} /> : null}
      {children}
    </>
  )
}

function getApiErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    const detail =
      typeof error.body === "object" &&
      error.body !== null &&
      "detail" in error.body
        ? error.body.detail
        : null
    return typeof detail === "string" ? detail : error.message
  }

  return error instanceof Error ? error.message : "Request failed"
}

export function PlayerFollowContextMenuItem({
  menuOpen,
  steamid64,
  testId = "player-follow-menu-item",
}: {
  menuOpen: boolean
  steamid64: string
  testId?: string
}) {
  const authenticated = isLoggedIn()
  const viewerSteamid64 = authenticated
    ? getSteamid64FromAccessToken(localStorage.getItem("access_token"))
    : null
  const { user } = useAuth()
  const { showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()
  const followSummaryQuery = useQuery({
    queryKey: ["profile-follow-summary", steamid64],
    queryFn: () =>
      PlayersService.readPlayerFollowSummary({
        identifier: steamid64,
      }),
    enabled: authenticated && menuOpen,
    retry: false,
    staleTime: 30_000,
  })
  const followSummary = followSummaryQuery.data
  const isOwnPlayer =
    !authenticated ||
    viewerSteamid64 === steamid64 ||
    user?.steamid64 === steamid64 ||
    followSummary?.viewer_is_self === true
  const isFollowing = followSummary?.viewer_is_following === true
  const followMutation = useMutation({
    mutationFn: async () => {
      return isFollowing
        ? await PlayersService.unfollowPlayer({ identifier: steamid64 })
        : await PlayersService.followPlayer({ identifier: steamid64 })
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["profile-follow-summary", steamid64], data)
      void queryClient.invalidateQueries({
        queryKey: ["profile-follow-summary"],
      })
      void queryClient.invalidateQueries({
        queryKey: ["profile-social"],
      })
    },
    onError: (error) => {
      showErrorToast(getApiErrorMessage(error))
    },
  })

  if (!authenticated || isOwnPlayer) {
    return null
  }

  return (
    <>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        data-testid={testId}
        disabled={followSummaryQuery.isLoading || followMutation.isPending}
        onSelect={() => {
          if (followSummaryQuery.isLoading || followMutation.isPending) {
            return
          }
          followMutation.mutate()
        }}
      >
        {isFollowing ? <UserCheck /> : <UserPlus />}
        {followMutation.isPending
          ? "Updating follow"
          : isFollowing
            ? "Unfollow"
            : "Follow"}
      </DropdownMenuItem>
    </>
  )
}

export function PlayerDisplay({
  player,
  fallbackSteamid64,
  showSteamid = false,
  showCountryFlag = true,
  subline = null,
  className,
  nameMaxLength,
  disableProfileLink = false,
}: PlayerDisplayProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [avatarLoadFailed, setAvatarLoadFailed] = useState(false)
  const steamid64 = player?.steamid64 || fallbackSteamid64 || "N/A"
  const hydrationQuery = useQuery({
    queryKey: ["graphql", "player", steamid64],
    enabled: steamid64Pattern.test(steamid64) && shouldHydratePlayer(player),
    queryFn: () => loadPlayerForDisplay(steamid64),
    staleTime: 60_000,
  })
  const resolvedPlayer = hydrationQuery.data ?? player
  const showWebsiteUserRing = hasWebsiteUserAvatarRing(resolvedPlayer)
  const hasProfileLink = !disableProfileLink && steamid64Pattern.test(steamid64)
  const displayName = getPlayerDisplayName(resolvedPlayer, steamid64)
  const truncatedDisplayName = truncateText(displayName, nameMaxLength)
  const effectiveSubline =
    subline ?? (showSteamid ? ({ type: "steamid64" } as const) : null)
  const avatarHash = getPlayerAvatarHash(resolvedPlayer)
  const steamAvatarSrc = avatarHash
    ? `https://avatars.steamstatic.com/${avatarHash}_full.jpg`
    : null
  const avatarSrc =
    avatarLoadFailed || !steamAvatarSrc
      ? playerAvatarPlaceholderSrc
      : steamAvatarSrc
  const steamProfileUrl = hasProfileLink
    ? `https://steamcommunity.com/profiles/${steamid64}`
    : null

  const countryCode = resolvedPlayer?.country?.toUpperCase() || null
  const FlagComponent = countryCode ? flagComponents[countryCode] : null
  const countryName =
    countryCode && countryNameFormatter
      ? countryNameFormatter.of(countryCode) || countryCode
      : countryCode
  const wrSublineQuery = useQuery({
    queryKey: [
      "player-display",
      "wr-subline",
      effectiveSubline?.type === "wr"
        ? (effectiveSubline.scope ?? "OVR")
        : null,
      effectiveSubline?.type === "wr"
        ? (effectiveSubline.recordType ?? "NUB")
        : null,
    ],
    enabled:
      effectiveSubline?.type === "wr" &&
      (effectiveSubline.mapId != null ||
        Boolean(effectiveSubline.mapName?.trim())),
    queryFn: async () =>
      await MapsService.readMapWrs({
        scope: effectiveSubline?.type === "wr" ? effectiveSubline.scope : "OVR",
        type:
          effectiveSubline?.type === "wr" ? effectiveSubline.recordType : "NUB",
      }),
    staleTime: 60_000,
  })

  useEffect(() => {
    setAvatarLoadFailed(false)
  }, [])

  let sublineContent: string | null = null
  if (effectiveSubline?.type === "steamid64") {
    sublineContent = steamid64
  } else if (effectiveSubline?.type === "text") {
    sublineContent = effectiveSubline.value?.trim() || null
  } else if (effectiveSubline?.type === "wr") {
    const matchingWr = wrSublineQuery.data?.find(
      (record) =>
        record.player.steamid64 === steamid64 &&
        effectiveSubline.mapId != null &&
        record.map_id === effectiveSubline.mapId,
    )

    if (matchingWr) {
      sublineContent = `WR: ${formatRecordTime(matchingWr.time)}`
    } else if (wrSublineQuery.isLoading) {
      sublineContent = "WR: ..."
    } else if (effectiveSubline.emptyLabel !== undefined) {
      sublineContent = effectiveSubline.emptyLabel
    }
  }

  const content = (
    <div
      className={cn(
        "flex min-w-0 items-center gap-2.5 transition-colors",
        hasProfileLink &&
          "group-hover:text-foreground group-focus-visible:text-foreground",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        {showCountryFlag ? (
          FlagComponent ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  className="inline-flex"
                  data-testid={`country-flag-${steamid64}`}
                  role="img"
                  aria-label={countryName || countryCode || "Unknown country"}
                >
                  <FlagComponent className="h-4 w-6 shrink-0" />
                </span>
              </TooltipTrigger>
              <TooltipContent sideOffset={8}>
                {countryName || countryCode}
              </TooltipContent>
            </Tooltip>
          ) : (
            <img
              src={noneFlagSrc}
              alt="Unknown country"
              className="h-4 w-6 shrink-0 rounded-[2px] border border-border/80"
              title="Unknown country"
            />
          )
        ) : null}

        <Avatar
          data-testid={
            showWebsiteUserRing ? `player-avatar-ring-${steamid64}` : undefined
          }
          className={cn(
            "size-8 rounded-lg transition-transform duration-200",
            showWebsiteUserRing &&
              "ring-2 ring-pink-400/90 ring-offset-2 ring-offset-background",
            hasProfileLink &&
              "group-hover:scale-[1.03] group-focus-visible:scale-[1.03]",
          )}
        >
          <AvatarImage
            src={avatarSrc}
            alt={`${displayName} avatar`}
            onError={() => {
              setAvatarLoadFailed(true)
            }}
          />
          <AvatarFallback className="rounded-lg bg-zinc-600 text-white">
            {getInitials(displayName)}
          </AvatarFallback>
        </Avatar>
      </div>

      <div className="min-w-0">
        <p
          className={cn(
            "w-full truncate text-sm font-medium transition-colors",
            hasProfileLink &&
              "group-hover:text-accent-foreground group-focus-visible:text-accent-foreground",
          )}
          title={displayName}
        >
          {truncatedDisplayName}
        </p>
        {sublineContent ? (
          <p
            className={cn(
              "w-full truncate text-xs text-muted-foreground",
              effectiveSubline?.type === "steamid64" && "font-mono",
            )}
            title={sublineContent}
          >
            {sublineContent}
          </p>
        ) : null}
      </div>
    </div>
  )

  const handleContextMenu = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    setMenuOpen(true)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLAnchorElement>) => {
    if (
      event.key === "ContextMenu" ||
      (event.shiftKey && event.key === "F10")
    ) {
      event.preventDefault()
      setMenuOpen(true)
    }
  }

  if (!hasProfileLink) {
    return content
  }

  return (
    <DropdownMenu modal={false} open={menuOpen} onOpenChange={setMenuOpen}>
      <div className="relative">
        <DropdownMenuTrigger asChild>
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 block"
          />
        </DropdownMenuTrigger>
        <Link
          to="/profile/$identifier"
          params={{ identifier: steamid64 }}
          className="-mx-2 -my-1 block rounded-md px-2 py-1 transition-colors hover:bg-accent/70 focus-visible:bg-accent/70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          onContextMenu={handleContextMenu}
          onKeyDown={handleKeyDown}
        >
          {content}
        </Link>
      </div>
      <DropdownMenuContent
        side="right"
        align="start"
        sideOffset={10}
        className="min-w-44"
      >
        <PlayerContextMenuItems
          displayName={displayName}
          hasProfileLink={hasProfileLink}
          player={
            resolvedPlayer
              ? {
                  alias: resolvedPlayer.alias,
                  country: resolvedPlayer.country,
                  name: resolvedPlayer.name ?? displayName,
                  steamid64,
                }
              : undefined
          }
          steamProfileUrl={steamProfileUrl}
          steamid64={steamid64}
        >
          <PlayerFollowContextMenuItem
            menuOpen={menuOpen}
            steamid64={steamid64}
          />
        </PlayerContextMenuItems>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
