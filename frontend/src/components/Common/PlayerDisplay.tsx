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
import { ApiError, PlayersService } from "@/client"
import EditPlayer from "@/components/AdminPlayers/EditPlayer"
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

interface PlayerDisplayProps {
  player?: {
    steamid64: string
    name: string
    alias?: string | null
    avatar_hash?: string | null
    country?: string | null
    is_website_user?: boolean
  } | null
  fallbackSteamid64?: string
  showSteamid?: boolean
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

function hasWebsiteUserAvatarRing(player: PlayerDisplayProps["player"]): boolean {
  return player?.is_website_user === true
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
  className,
  nameMaxLength,
  disableProfileLink = false,
}: PlayerDisplayProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [avatarLoadFailed, setAvatarLoadFailed] = useState(false)
  const showWebsiteUserRing = hasWebsiteUserAvatarRing(player)
  const steamid64 = player?.steamid64 || fallbackSteamid64 || "N/A"
  const hasProfileLink = !disableProfileLink && steamid64Pattern.test(steamid64)
  const displayName = player?.alias || player?.name || steamid64
  const truncatedDisplayName = truncateText(displayName, nameMaxLength)
  const steamAvatarSrc = player?.avatar_hash
    ? `https://avatars.steamstatic.com/${player.avatar_hash}_full.jpg`
    : null
  const avatarSrc =
    avatarLoadFailed || !steamAvatarSrc
      ? playerAvatarPlaceholderSrc
      : steamAvatarSrc
  const steamProfileUrl = hasProfileLink
    ? `https://steamcommunity.com/profiles/${steamid64}`
    : null

  const countryCode = player?.country?.toUpperCase() || null
  const FlagComponent = countryCode ? flagComponents[countryCode] : null
  const countryName =
    countryCode && countryNameFormatter
      ? countryNameFormatter.of(countryCode) || countryCode
      : countryCode

  useEffect(() => {
    setAvatarLoadFailed(false)
  }, [])

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
        {FlagComponent ? (
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
        )}

        <Avatar
          data-testid={
            showWebsiteUserRing ? `player-avatar-ring-${steamid64}` : undefined
          }
          className={cn(
            "size-8 rounded-md transition-transform duration-200",
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
          <AvatarFallback className="rounded-md bg-zinc-600 text-white">
            {getInitials(displayName)}
          </AvatarFallback>
        </Avatar>
      </div>

      <div className="min-w-0">
        <p
          className={cn(
            "truncate font-medium transition-colors",
            hasProfileLink &&
              "group-hover:text-accent-foreground group-focus-visible:text-accent-foreground",
          )}
          title={displayName}
        >
          {truncatedDisplayName}
        </p>
        {showSteamid && (
          <p className="truncate font-mono text-xs text-muted-foreground">
            {steamid64}
          </p>
        )}
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
          player={player ?? undefined}
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
