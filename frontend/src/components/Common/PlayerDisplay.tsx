import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "@tanstack/react-router"
import * as Flags from "country-flag-icons/react/3x2"
import {
  Copy,
  ExternalLink,
  Flag,
  History,
  IdCard,
  ShieldAlert,
  UserCheck,
  UserPlus,
  UserRound,
  Users,
} from "lucide-react"
import type {
  ComponentType,
  KeyboardEvent,
  MouseEvent,
  ReactNode,
  SVGProps,
} from "react"
import { Children, lazy, Suspense, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import noneFlagSrc from "@/assets/flags/none.svg"
import playerAvatarPlaceholderSrc from "@/assets/player-avatar-placeholder.jpg"
import {
  ApiError,
  MapsService,
  type ModeScope,
  PlayerFollowsService,
  type RecordType,
  type UserRole,
} from "@/client"
import EditPlayer from "@/components/AdminPlayers/EditPlayer"
import { suppressRowInteractions } from "@/components/Common/interaction-suppression"
import {
  getPlayerRatingBadgeIcon,
  getPlayerRatingLevel,
} from "@/components/Common/player-rating"
import { usePlayerDisplayPreferences } from "@/components/player-display-preferences-provider"
import { formatRecordTime } from "@/components/Records/utils"
import { useScope } from "@/components/scope-provider"
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
import {
  canModerateBansAndRecords,
  getHighestPlayerPermission,
  isSuperuser,
  PLAYER_PERMISSION_RING_CLASS_NAMES,
} from "@/lib/user-roles"
import { cn, truncateText } from "@/lib/utils"
import { getInitials } from "@/utils"

import { ProfileHistoryDialog } from "../Profile/ProfileHistoryDialog"
import { getProfileFriendsQueryOptions } from "../Profile/profile-utils"
import {
  ReportPlayerDialog,
  type ReportRecordContext,
} from "../Reports/ReportPlayerDialog"

const AddBanDialog = lazy(async () => {
  const module = await import("../Bans/AddBanDialog")
  return { default: module.AddBanDialog }
})

const countryNameFormatter =
  typeof Intl !== "undefined" && "DisplayNames" in Intl
    ? new Intl.DisplayNames(["en"], { type: "region" })
    : null

const flagComponents = Flags as Record<
  string,
  ComponentType<SVGProps<SVGSVGElement>>
>
const steamid64Pattern = /^\d{17}$/

function isUnknownSteamid64(steamid64?: string | null): boolean {
  return steamid64 === "0"
}

export type PlayerDisplayPlayer = {
  steamid64: string
  displayName?: string | null
  display_name?: string | null
  name?: string | null
  tag?: string | null
  clanTag?: string | null
  clan_tag?: string | null
  alias?: string | null
  customId?: string | null
  custom_id?: string | null
  avatarHash?: string | null
  avatar_hash?: string | null
  country?: string | null
  roles?: UserRole[] | null
  primaryScope?: ModeScope | null
  primary_scope?: ModeScope | null
  rating?: number | null
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
      scope?: ModeScope
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
  compact?: boolean
  nameMaxLength?: number
  disableProfileLink?: boolean
  hideAvatarWithoutSteamid64?: boolean
  reportRecordContext?: ReportRecordContext | null
  scope?: ModeScope
}

type PlayerContextMenuItemsProps = {
  adminChildren?: ReactNode
  closeMenu: () => void
  displayName: string
  hasProfileLink: boolean
  loggedInChildren?: ReactNode
  onAddBan: () => void
  player?: {
    alias?: string | null
    country?: string | null
    name: string
    steamid64: string
  }
  steamProfileUrl: string | null
  steamid64: string
}

export function getPlayerDisplayName(
  player?: PlayerDisplayPlayer | null,
  fallbackSteamid64?: string,
): string {
  const steamid64 = player?.steamid64 || fallbackSteamid64
  const displayName =
    player?.displayName?.trim() || player?.display_name?.trim()
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

  if (isUnknownSteamid64(steamid64)) {
    return "Unknown"
  }

  return "Unknown"
}

function getPlayerAvatarHash(
  player?: PlayerDisplayPlayer | null,
): string | null {
  return player?.avatarHash ?? player?.avatar_hash ?? null
}

function getPlayerClanTag(player?: PlayerDisplayPlayer | null): string | null {
  const clanTag =
    player?.clanTag?.trim() ?? player?.clan_tag?.trim() ?? player?.tag?.trim()
  return clanTag ? clanTag : null
}

export function PlayerContextMenuItems({
  adminChildren,
  closeMenu,
  displayName,
  hasProfileLink,
  loggedInChildren,
  onAddBan,
  player,
  steamProfileUrl,
  steamid64,
}: PlayerContextMenuItemsProps) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { user } = useAuth()
  const [, copyToClipboard] = useCopyToClipboard()
  const canAddBan =
    canModerateBansAndRecords(user) && steamid64Pattern.test(steamid64)
  const canViewProfileHistory =
    isSuperuser(user) && steamid64Pattern.test(steamid64)
  const adminItems = Children.toArray(adminChildren)
  const loggedInItems = Children.toArray(loggedInChildren)
  const hasAdminSection =
    canAddBan ||
    canViewProfileHistory ||
    (player != null && isSuperuser(user)) ||
    adminItems.length > 0
  const hasLoggedInSection = loggedInItems.length > 0
  const [profileHistoryOpen, setProfileHistoryOpen] = useState(false)

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
      {hasLoggedInSection ? (
        <>
          <DropdownMenuSeparator />
          {loggedInItems}
        </>
      ) : null}
      {hasAdminSection ? (
        <>
          <DropdownMenuSeparator />
          {player ? <EditPlayer player={player} /> : null}
          {canViewProfileHistory ? (
            <DropdownMenuItem
              data-testid="profile-history-menu-item"
              onSelect={(event) => {
                event.preventDefault()
                closeMenu()
                setProfileHistoryOpen(true)
              }}
            >
              <History />
              {t("profile.history.menuAction")}
            </DropdownMenuItem>
          ) : null}
          {adminItems}
          {canAddBan ? (
            <DropdownMenuItem
              variant="destructive"
              onSelect={(event) => {
                event.preventDefault()
                closeMenu()
                onAddBan()
              }}
            >
              <ShieldAlert />
              Add Ban
            </DropdownMenuItem>
          ) : null}
        </>
      ) : null}
      <ProfileHistoryDialog
        identifier={steamid64}
        onOpenChange={setProfileHistoryOpen}
        open={profileHistoryOpen}
      />
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
      PlayerFollowsService.readPlayerFollowSummary({
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
        ? await PlayerFollowsService.unfollowPlayer({ identifier: steamid64 })
        : await PlayerFollowsService.followPlayer({ identifier: steamid64 })
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
  )
}

export function PlayerDisplay({
  player,
  fallbackSteamid64,
  showSteamid = false,
  showCountryFlag = true,
  subline = null,
  className,
  compact = false,
  nameMaxLength,
  disableProfileLink = false,
  hideAvatarWithoutSteamid64 = false,
  reportRecordContext = null,
  scope,
}: PlayerDisplayProps) {
  const { t } = useTranslation()
  const { scope: appScope } = useScope()
  const playerDisplayPreferences = usePlayerDisplayPreferences()
  const effectiveHydrationScope =
    scope ??
    (playerDisplayPreferences.ratingIconScope === "global"
      ? appScope
      : undefined)
  const [menuOpen, setMenuOpen] = useState(false)
  const [addBanDialogOpen, setAddBanDialogOpen] = useState(false)
  const [reportDialogOpen, setReportDialogOpen] = useState(false)
  const [avatarLoadFailed, setAvatarLoadFailed] = useState(false)
  const suppressProfileLinkClickRef = useRef(false)
  const steamid64 = player?.steamid64 || fallbackSteamid64 || "N/A"
  const hydrationQuery = useQuery({
    queryKey: [
      "graphql",
      "player",
      steamid64,
      effectiveHydrationScope ?? "PRIMARY",
    ],
    enabled: steamid64Pattern.test(steamid64),
    queryFn: () => loadPlayerForDisplay(steamid64, effectiveHydrationScope),
    staleTime: 60_000,
  })
  const resolvedPlayer: PlayerDisplayPlayer | undefined =
    hydrationQuery.data || player
      ? {
          steamid64,
          ...player,
          ...hydrationQuery.data,
        }
      : undefined
  const highestPermission = getHighestPlayerPermission(resolvedPlayer?.roles)
  const showRoleRing = highestPermission !== null
  const hasProfileLink = !disableProfileLink && steamid64Pattern.test(steamid64)
  const displayName = getPlayerDisplayName(resolvedPlayer, steamid64)
  const truncatedDisplayName = truncateText(displayName, nameMaxLength)
  const authenticated = isLoggedIn()
  const viewerSteamid64 = authenticated
    ? getSteamid64FromAccessToken(localStorage.getItem("access_token"))
    : null
  const { user } = useAuth()
  const isCurrentUser =
    steamid64Pattern.test(steamid64) &&
    (viewerSteamid64 === steamid64 || user?.steamid64 === steamid64)
  const viewerFriendsQuery = useQuery({
    ...getProfileFriendsQueryOptions(viewerSteamid64),
    enabled:
      viewerSteamid64 !== null &&
      steamid64Pattern.test(steamid64) &&
      viewerSteamid64 !== steamid64,
  })
  const isViewerFriend =
    viewerFriendsQuery.data?.data.some(
      (friend) => friend.steamid64 === steamid64,
    ) ?? false
  const effectiveSubline =
    subline ?? (showSteamid ? ({ type: "steamid64" } as const) : null)
  const clanTag = getPlayerClanTag(resolvedPlayer)
  const fullDisplayLabel = clanTag ? `${clanTag}${displayName}` : displayName
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
  const showAvatar =
    !hideAvatarWithoutSteamid64 || steamid64Pattern.test(steamid64)

  const countryCode = resolvedPlayer?.country?.toUpperCase() || null
  const FlagComponent = countryCode ? flagComponents[countryCode] : null
  const countryName =
    countryCode && countryNameFormatter
      ? countryNameFormatter.of(countryCode) || countryCode
      : countryCode
  const rating = resolvedPlayer?.rating
  const showEffectiveCountryFlag =
    showCountryFlag && playerDisplayPreferences.showCountryFlag
  const showRatingBadge =
    playerDisplayPreferences.showRatingIcon &&
    rating !== undefined &&
    rating !== null
  const ratingLevel = showRatingBadge ? getPlayerRatingLevel(rating) : null
  const ratingBadgeSrc =
    ratingLevel !== null ? getPlayerRatingBadgeIcon(ratingLevel) : null
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

  useEffect(() => {
    if (menuOpen || !suppressProfileLinkClickRef.current) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      suppressProfileLinkClickRef.current = false
    }, 0)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [menuOpen])

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
      data-drag-scroll-ignore
      data-current-user={isCurrentUser ? "true" : undefined}
      className={cn(
        "flex min-w-0 items-center transition-colors",
        compact ? "gap-2" : "gap-2.5",
        hasProfileLink &&
          "group-hover:text-foreground group-focus-visible:text-foreground",
        className,
      )}
    >
      <div className={cn("flex items-center", compact ? "gap-1.5" : "gap-2")}>
        <div className="flex items-center gap-1">
          {showEffectiveCountryFlag ? (
            FlagComponent ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    className="inline-flex"
                    data-testid={`country-flag-${steamid64}`}
                    role="img"
                    aria-label={countryName || countryCode || "Unknown country"}
                  >
                    <FlagComponent
                      className={cn(
                        "shrink-0",
                        compact ? "h-3.5 w-5" : "h-4 w-6",
                      )}
                    />
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
                className={cn(
                  "shrink-0 rounded-[2px] border border-border/80",
                  compact ? "h-3.5 w-5" : "h-4 w-6",
                )}
                title="Unknown country"
              />
            )
          ) : null}

          {showRatingBadge ? (
            <span
              className={cn(
                "inline-flex shrink-0 items-center justify-center",
                compact ? "h-4 w-4" : "h-5 w-5",
              )}
            >
              {ratingBadgeSrc ? (
                <img
                  src={ratingBadgeSrc}
                  alt={`Rating level ${ratingLevel}`}
                  data-testid={`rating-icon-${steamid64}`}
                  className={cn("shrink-0", compact ? "h-4 w-4" : "h-5 w-5")}
                />
              ) : null}
            </span>
          ) : null}
        </div>

        {showAvatar ? (
          <Avatar
            data-testid={
              showRoleRing ? `player-avatar-ring-${steamid64}` : undefined
            }
            className={cn(
              "transition-transform duration-200",
              compact ? "size-6 rounded-md" : "size-8 rounded-lg",
              showRoleRing &&
                (compact
                  ? "ring-2 ring-offset-1 ring-offset-background"
                  : "ring-2 ring-offset-2 ring-offset-background"),
              highestPermission &&
                PLAYER_PERMISSION_RING_CLASS_NAMES[highestPermission],
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
            <AvatarFallback
              className={cn(
                "bg-zinc-600 text-white",
                compact ? "rounded-md" : "rounded-lg",
              )}
            >
              {getInitials(displayName)}
            </AvatarFallback>
          </Avatar>
        ) : null}
      </div>

      <div className="min-w-0">
        <p
          className={cn(
            "flex w-full min-w-0 items-center gap-1 text-sm font-medium transition-colors",
            hasProfileLink &&
              "group-hover:text-accent-foreground group-focus-visible:text-accent-foreground",
          )}
          title={fullDisplayLabel}
        >
          {clanTag ? (
            <span className="shrink-0 whitespace-pre text-muted-foreground">
              {clanTag}
            </span>
          ) : null}
          <span className="truncate">{truncatedDisplayName}</span>
          {isViewerFriend ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  className="shrink-0 text-muted-foreground"
                  role="img"
                  aria-label={t("leaderboards.players.friends.label")}
                >
                  <Users className="h-3.5 w-3.5" />
                </span>
              </TooltipTrigger>
              <TooltipContent sideOffset={8}>
                {t("leaderboards.players.friends.label")}
              </TooltipContent>
            </Tooltip>
          ) : null}
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
    event.stopPropagation()
    suppressProfileLinkClickRef.current = true
    setMenuOpen(true)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLAnchorElement>) => {
    if (
      event.key === "ContextMenu" ||
      (event.shiftKey && event.key === "F10")
    ) {
      event.preventDefault()
      event.stopPropagation()
      suppressProfileLinkClickRef.current = true
      setMenuOpen(true)
    }
  }

  const handleLinkClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!suppressProfileLinkClickRef.current) {
      return
    }

    event.preventDefault()
    event.stopPropagation()
  }

  const handleAddBanDialogOpenChange = (open: boolean) => {
    if (!open) {
      suppressRowInteractions()
    }
    setAddBanDialogOpen(open)
  }

  const handleReportDialogOpenChange = (open: boolean) => {
    if (!open) {
      suppressRowInteractions()
    }
    setReportDialogOpen(open)
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
          onClick={handleLinkClick}
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
        onClick={(event) => event.stopPropagation()}
        onPointerDown={(event) => event.stopPropagation()}
        onKeyDown={(event) => event.stopPropagation()}
      >
        <PlayerContextMenuItems
          loggedInChildren={
            authenticated && steamid64Pattern.test(steamid64) ? (
              <>
                <DropdownMenuItem
                  data-testid="report-player-menu-item"
                  variant="destructive"
                  onSelect={(event) => {
                    event.preventDefault()
                    setMenuOpen(false)
                    setReportDialogOpen(true)
                  }}
                >
                  <Flag />
                  Report Player
                </DropdownMenuItem>
                {!isCurrentUser ? (
                  <PlayerFollowContextMenuItem
                    menuOpen={menuOpen}
                    steamid64={steamid64}
                  />
                ) : null}
              </>
            ) : undefined
          }
          closeMenu={() => setMenuOpen(false)}
          displayName={displayName}
          hasProfileLink={hasProfileLink}
          onAddBan={() => setAddBanDialogOpen(true)}
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
        />
      </DropdownMenuContent>
      <ReportPlayerDialog
        open={reportDialogOpen}
        onOpenChange={handleReportDialogOpenChange}
        recordContext={reportRecordContext}
        target={{
          steamid64,
          displayName,
          player: resolvedPlayer,
        }}
      />
      <Suspense fallback={null}>
        <AddBanDialog
          open={addBanDialogOpen}
          onOpenChange={handleAddBanDialogOpenChange}
          initialPlayer={{
            steamid64,
            displayName,
            name: resolvedPlayer?.name ?? displayName,
            alias: resolvedPlayer?.alias ?? null,
            country: resolvedPlayer?.country ?? null,
          }}
        />
      </Suspense>
    </DropdownMenu>
  )
}
