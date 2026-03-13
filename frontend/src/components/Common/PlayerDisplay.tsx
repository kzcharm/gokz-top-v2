import * as Flags from "country-flag-icons/react/3x2"
import type { ComponentType, SVGProps } from "react"

import type { PlayerPublic } from "@/client"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { getInitials } from "@/utils"

const countryNameFormatter =
  typeof Intl !== "undefined" && "DisplayNames" in Intl
    ? new Intl.DisplayNames(["en"], { type: "region" })
    : null

const flagComponents = Flags as Record<
  string,
  ComponentType<SVGProps<SVGSVGElement>>
>

interface PlayerDisplayProps {
  player?: PlayerPublic | null
  fallbackSteamid64?: string
  showSteamid?: boolean
  className?: string
}

export function PlayerDisplay({
  player,
  fallbackSteamid64,
  showSteamid = false,
  className,
}: PlayerDisplayProps) {
  const steamid64 = player?.steamid64 || fallbackSteamid64 || "N/A"
  const displayName = player?.alias || player?.name || steamid64
  const avatarSrc = player?.avatar_hash
    ? `https://avatars.steamstatic.com/${player.avatar_hash}_full.jpg`
    : undefined

  const countryCode = player?.country?.toUpperCase() || null
  const FlagComponent = countryCode ? flagComponents[countryCode] : null
  const countryName =
    countryCode && countryNameFormatter
      ? countryNameFormatter.of(countryCode) || countryCode
      : countryCode

  return (
    <div className={cn("flex min-w-0 items-center gap-2.5", className)}>
      <div className="flex items-center gap-2">
        {FlagComponent ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="inline-flex appearance-none border-0 bg-transparent p-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                data-testid={`country-flag-${steamid64}`}
                aria-label={countryName || countryCode || "Unknown country"}
              >
                <FlagComponent className="h-4 w-6 shrink-0" />
              </button>
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

        <Avatar className="size-8 rounded-md">
          <AvatarImage src={avatarSrc} alt={`${displayName} avatar`} />
          <AvatarFallback className="rounded-md bg-zinc-600 text-white">
            {getInitials(displayName)}
          </AvatarFallback>
        </Avatar>
      </div>

      <div className="min-w-0">
        <p className="truncate font-medium">{displayName}</p>
        {showSteamid && (
          <p className="truncate font-mono text-xs text-muted-foreground">
            {steamid64}
          </p>
        )}
      </div>
    </div>
  )
}
