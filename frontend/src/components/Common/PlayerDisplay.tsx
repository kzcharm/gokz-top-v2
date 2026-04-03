import { Link, useNavigate } from "@tanstack/react-router"
import * as Flags from "country-flag-icons/react/3x2"
import { Copy, ExternalLink, IdCard, UserRound } from "lucide-react"
import type { ComponentType, KeyboardEvent, MouseEvent, SVGProps } from "react"
import { useState } from "react"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
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
  } | null
  fallbackSteamid64?: string
  showSteamid?: boolean
  className?: string
  nameMaxLength?: number
}

export function PlayerDisplay({
  player,
  fallbackSteamid64,
  showSteamid = false,
  className,
  nameMaxLength,
}: PlayerDisplayProps) {
  const navigate = useNavigate()
  const [, copyToClipboard] = useCopyToClipboard()
  const [menuOpen, setMenuOpen] = useState(false)
  const steamid64 = player?.steamid64 || fallbackSteamid64 || "N/A"
  const hasProfileLink = steamid64Pattern.test(steamid64)
  const displayName = player?.alias || player?.name || steamid64
  const truncatedDisplayName = truncateText(displayName, nameMaxLength)
  const avatarSrc = player?.avatar_hash
    ? `https://avatars.steamstatic.com/${player.avatar_hash}_full.jpg`
    : undefined
  const steamProfileUrl = hasProfileLink
    ? `https://steamcommunity.com/profiles/${steamid64}`
    : null

  const countryCode = player?.country?.toUpperCase() || null
  const FlagComponent = countryCode ? flagComponents[countryCode] : null
  const countryName =
    countryCode && countryNameFormatter
      ? countryNameFormatter.of(countryCode) || countryCode
      : countryCode

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
          <span
            className="inline-flex h-4 w-6 items-center justify-center rounded-[2px] border text-[10px] font-semibold text-muted-foreground"
            title="Unknown country"
          >
            --
          </span>
        )}

        <Avatar
          className={cn(
            "size-8 rounded-md transition-transform duration-200",
            hasProfileLink &&
              "group-hover:scale-[1.03] group-focus-visible:scale-[1.03]",
          )}
        >
          <AvatarImage src={avatarSrc} alt={`${displayName} avatar`} />
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

  const handleGotoProfile = () => {
    if (!hasProfileLink) {
      return
    }

    void navigate({ to: "/profile/$steamid64", params: { steamid64 } })
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
          to="/profile/$steamid64"
          params={{ steamid64 }}
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
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
