import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  Copy,
  Eye,
  Heart,
  InfoIcon,
  Search,
  UserCheck,
  UserPlus,
  UserRoundCheck,
  X,
} from "lucide-react"
import {
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  useDeferredValue,
  useEffect,
  useRef,
  useState,
} from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import {
  type PlayerFollowSummaryPublic,
  PlayerFollowsService,
  PlayerSocialLinksService,
  PlayersService,
} from "@/client"
import { AddBanDialog } from "@/components/Bans/AddBanDialog"
import { CountryFlag } from "@/components/Common/CountryFlag"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import {
  getPlayerDisplayName,
  PlayerContextMenuItems,
  PlayerDisplay,
  PlayerFollowContextMenuItem,
} from "@/components/Common/PlayerDisplay"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import { getSteamid64FromAccessToken } from "@/lib/auth"
import { type GraphqlPlayer, searchPlayersGraphql } from "@/lib/player-graphql"
import { getSocialPlatformLabel, SocialPlatformIcon } from "@/lib/social-links"
import {
  getHighestPlayerPermission,
  PLAYER_PERMISSION_RING_CLASS_NAMES,
} from "@/lib/user-roles"
import { cn } from "@/lib/utils"
import { getInitials } from "@/utils"

import {
  ProfileSocialDialog,
  type ProfileSocialTab,
} from "./ProfileSocialDialog"
import { profileHomePlaceholder } from "./profile-home-placeholder"
import {
  getRatingRankLadder,
  getRatingRankLevel,
  ratingRankBadgeClasses,
} from "./profile-ranks"
import {
  formatNumber,
  formatRating,
  formatSecondsAsHours,
  getAvatarUrl,
  getFollowSummaryCount,
  getProfileFollowSummaryQueryOptions,
  type ProfilePlayer,
  type ProfileSummaryData,
} from "./profile-utils"

function formatJumpDistance(value: number) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

type RatingLadderEntry = ReturnType<typeof getRatingRankLadder>[number]

function getRatingMarkerTopPercent(
  rating: number,
  ladder: RatingLadderEntry[],
) {
  if (rating >= ladder[0].minimumRating) {
    return 0
  }

  const lastRank = ladder[ladder.length - 1]
  if (rating <= lastRank.minimumRating) {
    return 100
  }

  for (let index = 0; index < ladder.length - 1; index += 1) {
    const upperRank = ladder[index]
    const lowerRank = ladder[index + 1]

    if (
      rating <= upperRank.minimumRating &&
      rating >= lowerRank.minimumRating
    ) {
      const upperTop = (index / (ladder.length - 1)) * 100
      const lowerTop = ((index + 1) / (ladder.length - 1)) * 100
      const ratingSpan = upperRank.minimumRating - lowerRank.minimumRating
      const rankProgress =
        ratingSpan === 0
          ? 0
          : (rating - lowerRank.minimumRating) / ratingSpan

      return lowerTop + (upperTop - lowerTop) * rankProgress
    }
  }

  return 100
}

function ProfileRatingLadderDialog({
  children,
  rating,
}: {
  children: ReactNode
  rating: number
}) {
  const { t } = useTranslation()
  const ladder = getRatingRankLadder()
  const activeLevel = getRatingRankLevel(rating)
  const markerTop = getRatingMarkerTopPercent(rating, ladder)
  const progressHeight = 100 - markerTop

  return (
    <Dialog>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="max-h-[min(86vh,44rem)] overflow-y-auto p-0 sm:max-w-md">
        <DialogHeader className="border-b border-border/70 px-6 py-5">
          <DialogTitle>{t("profile.ratingLadder.title")}</DialogTitle>
          <DialogDescription>
            {t("profile.ratingLadder.description", {
              rating: formatRating(rating),
            })}
          </DialogDescription>
        </DialogHeader>
        <div className="px-6 pb-6 pt-5">
          <div className="relative space-y-2 pr-9">
            <div
              className="absolute bottom-6 right-2 top-6 w-1 rounded-full bg-muted"
              aria-hidden="true"
            >
              <div
                className="absolute bottom-0 left-0 w-full rounded-full bg-primary"
                style={{ height: `${progressHeight}%` }}
              />
              <div
                className="-left-1.5 absolute size-4 rounded-full border-2 border-background bg-primary shadow-sm shadow-primary/30"
                style={{ top: `calc(${markerTop}% - 0.5rem)` }}
              />
            </div>

            {ladder.map((rank) => {
              const isActive = rank.level === activeLevel

              return (
                <div
                  key={rank.level}
                  className={cn(
                    "grid min-h-12 grid-cols-[minmax(0,1fr)_auto] items-center gap-4 rounded-md border px-4 py-2 transition-colors",
                    isActive
                      ? "border-primary/70 bg-transparent"
                      : "border-transparent bg-transparent",
                  )}
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <img
                      src={rank.iconSrc}
                      alt=""
                      className="size-7 shrink-0"
                      aria-hidden="true"
                    />
                    <span className="truncate text-sm font-semibold">
                      {rank.name}
                    </span>
                  </div>
                  <div className="flex items-baseline gap-2 text-right">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                      {t("profile.ratingLadder.ratingLabel")}
                    </span>
                    <span className="tabular-nums text-sm font-semibold">
                      {formatRating(rank.minimumRating)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ProfileIdentityCard({
  displayName,
  profileSummary,
  profileSummaryLoading,
  onContextMenuOpenChange,
  openContextMenu,
  player,
}: {
  displayName: string
  profileSummary: ProfileSummaryData
  profileSummaryLoading: boolean
  onContextMenuOpenChange: (open: boolean) => void
  openContextMenu: boolean
  player: ProfilePlayer
}) {
  const { t } = useTranslation()
  const authenticated = isLoggedIn()
  const { user } = useAuth()
  const [addBanDialogOpen, setAddBanDialogOpen] = useState(false)
  const avatarUrl = getAvatarUrl(player)
  const highestPermission = getHighestPlayerPermission(player.roles)
  const showRoleRing = highestPermission !== null
  const alias = player.alias?.trim() ?? ""
  const canonicalName = player.name.trim()
  const hasDistinctAlias =
    alias.length > 0 &&
    alias.toLocaleLowerCase() !== canonicalName.toLocaleLowerCase()
  const primaryName = hasDistinctAlias ? alias : canonicalName
  const secondaryName = hasDistinctAlias ? canonicalName : null
  const hasProfileLink = /^\d{17}$/.test(player.steamid64)
  const steamProfileUrl = hasProfileLink
    ? `https://steamcommunity.com/profiles/${player.steamid64}`
    : null
  const socialLinksQuery = useQuery({
    queryKey: ["player-social-links", player.steamid64],
    queryFn: () =>
      PlayerSocialLinksService.readPlayerSocialLinks({
        identifier: player.steamid64,
      }),
    enabled: hasProfileLink,
    staleTime: 60_000,
  })
  const socialLinks = socialLinksQuery.data?.data ?? []
  const regionalStandingPrefix =
    profileSummary.region ?? t("profile.regionFallback")
  const regionalStandingLabel =
    profileSummary.regionalStanding === null
      ? t("profile.unranked")
      : `${regionalStandingPrefix} #${formatNumber(profileSummary.regionalStanding)}`
  const rankBadgeClassName =
    profileSummary.rating === null
      ? "border-border/70 bg-background/80 text-foreground"
      : ratingRankBadgeClasses[getRatingRankLevel(profileSummary.rating)]
  const viewerSteamid64 = authenticated
    ? getSteamid64FromAccessToken(localStorage.getItem("access_token"))
    : null
  const isCurrentUser =
    viewerSteamid64 === player.steamid64 || user?.steamid64 === player.steamid64

  const handleIdentityContextMenu = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    onContextMenuOpenChange(true)
  }

  const handleIdentityKeyDown = (event: KeyboardEvent<HTMLAnchorElement>) => {
    if (
      event.key !== "ContextMenu" &&
      !(event.shiftKey && event.key === "F10")
    ) {
      return
    }

    event.preventDefault()
    onContextMenuOpenChange(true)
  }

  return (
    <DropdownMenu
      modal={false}
      open={openContextMenu}
      onOpenChange={onContextMenuOpenChange}
    >
      <Card className="h-full min-w-0 gap-0 overflow-hidden rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="relative space-y-6 p-6">
          <div className="absolute inset-x-0 top-0 h-40 bg-[radial-gradient(circle_at_top_left,rgba(127,119,221,0.2),transparent_42%),radial-gradient(circle_at_75%_20%,rgba(29,158,117,0.16),transparent_28%)]" />

          <div className="relative flex flex-col items-center gap-4 text-center">
            <div
              className={cn(
                "relative flex flex-col items-center gap-4 rounded-[24px]",
              )}
            >
              <div className="relative">
                <div className="absolute -inset-2 rounded-[28px] bg-[radial-gradient(circle,rgba(127,119,221,0.28),transparent_72%)] blur-2xl" />
                <Dialog>
                  <DialogTrigger asChild>
                    <button
                      type="button"
                      data-testid={
                        showRoleRing
                          ? `profile-avatar-ring-${player.steamid64}`
                          : undefined
                      }
                      className={cn(
                        "relative flex h-32 w-32 cursor-zoom-in items-center justify-center overflow-hidden rounded-[28px] border border-white/40 bg-gradient-to-br from-primary via-primary/85 to-emerald-500/85 shadow-lg shadow-primary/15 transition-transform hover:scale-[1.02] focus-visible:outline-none",
                        showRoleRing && "ring-4 ring-offset-4 ring-offset-card",
                        highestPermission &&
                          PLAYER_PERMISSION_RING_CLASS_NAMES[highestPermission],
                      )}
                      aria-label={t("profile.zoomAvatar", {
                        name: player.name,
                      })}
                    >
                      {avatarUrl ? (
                        <img
                          src={avatarUrl}
                          alt={t("profile.avatarAlt", { name: player.name })}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <span className="text-3xl font-semibold text-white">
                          {getInitials(player.alias || player.name)}
                        </span>
                      )}
                    </button>
                  </DialogTrigger>
                  <DialogContent
                    className="w-auto max-w-none border-0 bg-transparent p-0 shadow-none outline-none focus:outline-none focus-visible:outline-none sm:max-w-none"
                    showCloseButton={false}
                  >
                    <div className="flex justify-center overflow-hidden rounded-[24px]">
                      {avatarUrl ? (
                        <img
                          src={avatarUrl}
                          alt={t("profile.avatarAltEnlarged", {
                            name: player.name,
                          })}
                          className="h-[min(80vh,32rem)] w-[min(80vw,32rem)] rounded-[24px] object-cover"
                        />
                      ) : (
                        <div className="flex h-[min(80vh,32rem)] w-[min(80vw,32rem)] items-center justify-center rounded-[24px] bg-gradient-to-br from-primary via-primary/85 to-emerald-500/85">
                          <span className="text-6xl font-semibold text-white">
                            {getInitials(player.alias || player.name)}
                          </span>
                        </div>
                      )}
                    </div>
                  </DialogContent>
                </Dialog>
              </div>

              <div className="space-y-2">
                <div className="space-y-1.5 pt-1">
                  <div className="flex items-center justify-center gap-2">
                    <CountryFlag
                      countryCode={player.country}
                      className="h-5 w-7 rounded-[4px]"
                      fallbackClassName="h-5 w-7 rounded-[4px]"
                      showTooltip={false}
                    />
                    {steamProfileUrl ? (
                      <div className="relative">
                        <DropdownMenuTrigger asChild>
                          <span
                            aria-hidden="true"
                            className="pointer-events-none absolute inset-0 block"
                          />
                        </DropdownMenuTrigger>
                        <a
                          href={steamProfileUrl}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={t("profile.openSteamProfile", {
                            name: primaryName,
                          })}
                          data-testid="profile-identity-surface"
                          className="rounded-[8px] text-3xl font-semibold tracking-tight transition-colors hover:text-primary focus-visible:text-primary focus-visible:outline-none"
                          onContextMenu={handleIdentityContextMenu}
                          onKeyDown={handleIdentityKeyDown}
                        >
                          {primaryName}
                        </a>
                      </div>
                    ) : (
                      <h1 className="text-3xl font-semibold tracking-tight">
                        {primaryName}
                      </h1>
                    )}
                  </div>
                  {secondaryName ? (
                    <p className="text-sm text-muted-foreground">
                      {secondaryName}
                    </p>
                  ) : null}
                  {socialLinks.length > 0 ? (
                    <div
                      className="flex flex-wrap items-center justify-center gap-2 pt-1"
                      data-testid="profile-social-links"
                    >
                      {socialLinks.map((link) => {
                        const platformLabel = getSocialPlatformLabel(
                          link.platform,
                        )
                        return (
                          <Tooltip key={link.id}>
                            <TooltipTrigger asChild>
                              <a
                                href={link.url}
                                target="_blank"
                                rel="noreferrer"
                                aria-label={`${platformLabel}${link.verified ? "" : " unverified"} link for ${primaryName}`}
                                data-testid={`profile-social-link-${link.platform}`}
                                className={cn(
                                  "inline-flex size-8 items-center justify-center rounded-full border bg-background/80 text-foreground transition-colors hover:border-primary/70 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                                  link.verified
                                    ? "border-border/70"
                                    : "border-dashed border-muted-foreground/45 text-muted-foreground",
                                )}
                              >
                                <SocialPlatformIcon
                                  platform={link.platform}
                                  className="size-4"
                                />
                              </a>
                            </TooltipTrigger>
                            <TooltipContent sideOffset={6}>
                              {platformLabel}
                              {link.verified
                                ? ""
                                : ` · ${t("profile.socialUnverified")}`}
                            </TooltipContent>
                          </Tooltip>
                        )
                      })}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap justify-center gap-2 pt-2">
              {profileSummary.rating === null ? (
                <span
                  className={cn(
                    "inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold",
                    rankBadgeClassName,
                  )}
                >
                  {profileSummaryLoading ? "..." : t("profile.unranked")}
                </span>
              ) : (
                <ProfileRatingLadderDialog rating={profileSummary.rating}>
                  <button
                    type="button"
                    className={cn(
                      "inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold transition-transform hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                      rankBadgeClassName,
                    )}
                  >
                    {profileSummaryLoading
                      ? "..."
                      : `${profileSummary.rankLabel} ${formatRating(profileSummary.rating)}`}
                  </button>
                </ProfileRatingLadderDialog>
              )}
              <span className="inline-flex items-center rounded-full border border-border/70 bg-background/80 px-3 py-1 text-xs font-semibold text-foreground">
                {profileSummaryLoading
                  ? `${t("labels.points")} ...`
                  : `${formatNumber(profileSummary.totalPoints)} Pts`}
              </span>
              <span className="inline-flex items-center rounded-full border border-border/70 bg-background/80 px-3 py-1 text-xs font-semibold text-foreground">
                {t("profile.summary.global")}{" "}
                {profileSummaryLoading
                  ? "..."
                  : profileSummary.globalStanding === null
                    ? t("profile.unranked")
                    : `#${formatNumber(profileSummary.globalStanding)}`}
              </span>
              <span className="inline-flex items-center rounded-full border border-border/70 bg-background/80 px-3 py-1 text-xs font-semibold text-foreground">
                {profileSummaryLoading
                  ? `${t("profile.summary.regional")} ...`
                  : regionalStandingLabel}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      <DropdownMenuContent
        align="center"
        className="min-w-44"
        data-testid="profile-identity-context-menu"
        side="bottom"
        sideOffset={12}
      >
        <PlayerContextMenuItems
          closeMenu={() => onContextMenuOpenChange(false)}
          displayName={displayName}
          hasProfileLink={hasProfileLink}
          loggedInChildren={
            authenticated && !isCurrentUser ? (
              <PlayerFollowContextMenuItem
                menuOpen={openContextMenu}
                steamid64={player.steamid64}
                testId="profile-follow-menu-item"
              />
            ) : undefined
          }
          onAddBan={() => setAddBanDialogOpen(true)}
          player={player}
          steamProfileUrl={steamProfileUrl}
          steamid64={player.steamid64}
        />
      </DropdownMenuContent>
      <AddBanDialog
        open={addBanDialogOpen}
        onOpenChange={setAddBanDialogOpen}
        initialPlayer={{
          steamid64: player.steamid64,
          displayName,
          name: player.name,
          alias: player.alias ?? null,
          country: player.country ?? null,
        }}
      />
    </DropdownMenu>
  )
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-0.5 text-sm">
      <span className="shrink-0 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </span>
      <span className="min-w-0 break-words text-right text-sm font-semibold">
        {value}
      </span>
    </div>
  )
}

const steamUniverse = 1n
const steamId64Base = 76561197960265728n

function getSteamIdConversions(steamid64: string) {
  if (!/^\d{17}$/.test(steamid64)) {
    return null
  }

  const steamId64Value = BigInt(steamid64)
  const accountId = steamId64Value - steamId64Base

  if (accountId < 0n) {
    return null
  }

  const authServer = accountId % 2n
  const authId = accountId / 2n
  const steamId3 = `[U:${steamUniverse}:${accountId.toString()}]`
  const steamId2 = `STEAM_${steamUniverse}:${authServer.toString()}:${authId.toString()}`
  const friendCode = accountId.toString()

  return {
    friendCode,
    steamId2,
    steamId3,
    steamId64: steamid64,
  }
}

function SteamIdContextValue({ steamid64 }: { steamid64: string }) {
  const { t } = useTranslation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [, copyToClipboard] = useCopyToClipboard()
  const conversions = getSteamIdConversions(steamid64)

  if (!conversions) {
    return <span className="text-right text-sm font-semibold">{steamid64}</span>
  }

  const handleCopy = async (label: string, value: string) => {
    const didCopy = await copyToClipboard(value)

    if (didCopy) {
      toast.success(t("common.copied", { label }), {
        description: value,
      })
      return
    }

    toast.error(t("common.copyFailed", { label }), {
      description: value,
    })
  }

  const handleCopySteamId64 = () => {
    void handleCopy("SteamID64", steamid64)
  }

  const handleContextMenu = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setMenuOpen(true)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (
      event.key !== "ContextMenu" &&
      !(event.shiftKey && event.key === "F10")
    ) {
      return
    }

    event.preventDefault()
    event.stopPropagation()
    setMenuOpen(true)
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
        <button
          type="button"
          className="break-all rounded-[8px] text-right text-sm font-semibold transition-colors hover:text-primary focus-visible:text-primary focus-visible:outline-none"
          data-testid="profile-steamid64-context-trigger"
          onClick={handleCopySteamId64}
          onContextMenu={handleContextMenu}
          onKeyDown={handleKeyDown}
        >
          {steamid64}
        </button>
      </div>
      <DropdownMenuContent
        align="end"
        className="min-w-72"
        data-testid="profile-steamid-context-menu"
        side="bottom"
        sideOffset={8}
      >
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault()
            void handleCopy("SteamID2", conversions.steamId2)
          }}
        >
          <Copy />
          SteamID2
          <DropdownMenuShortcut>{conversions.steamId2}</DropdownMenuShortcut>
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault()
            void handleCopy("SteamID3", conversions.steamId3)
          }}
        >
          <Copy />
          SteamID3
          <DropdownMenuShortcut>{conversions.steamId3}</DropdownMenuShortcut>
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault()
            void handleCopy("Friend Code", conversions.friendCode)
          }}
        >
          <Copy />
          Friend Code
          <DropdownMenuShortcut>{conversions.friendCode}</DropdownMenuShortcut>
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault()
            void handleCopy("SteamID64", conversions.steamId64)
          }}
        >
          <Copy />
          SteamID64
          <DropdownMenuShortcut>{conversions.steamId64}</DropdownMenuShortcut>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function SummaryMiniCard({
  dataTestId,
  disabled = false,
  icon,
  iconClassName,
  label,
  labelHidden = false,
  onClick,
  value,
}: {
  dataTestId?: string
  disabled?: boolean
  icon?: ReactNode
  iconClassName?: string
  label: string
  labelHidden?: boolean
  onClick?: () => void
  value: ReactNode
}) {
  const Comp = onClick ? "button" : "div"

  return (
    <Comp
      aria-label={label}
      className={cn(
        "rounded-[16px] border border-border/70 bg-background/65 px-3 py-2.5 text-left transition-colors",
        onClick
          ? "cursor-pointer hover:bg-background/90 focus-visible:bg-background/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-default disabled:hover:bg-background/65 disabled:opacity-70"
          : "",
      )}
      data-testid={dataTestId}
      disabled={onClick ? disabled : undefined}
      onClick={onClick}
      type={onClick ? "button" : undefined}
    >
      {icon ? (
        <div className="flex items-center gap-2.5">
          <span
            className={cn(
              "inline-flex items-center justify-center text-muted-foreground",
              iconClassName,
            )}
          >
            {icon}
          </span>
          <p
            className={cn(
              "min-w-0 text-xs text-muted-foreground",
              labelHidden && "sr-only",
            )}
          >
            {label}
          </p>
          <p className="ml-auto text-lg font-semibold tracking-tight">
            {value}
          </p>
        </div>
      ) : (
        <>
          <p className="text-lg font-semibold tracking-tight">{value}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
        </>
      )}
    </Comp>
  )
}

function SkillRadar() {
  const { t } = useTranslation()
  const size = 220
  const center = size / 2
  const radius = 74
  const labels = profileHomePlaceholder.skills.map((skill) => ({
    ...skill,
    label: t(
      `profile.skillRadar.${skill.label.toLowerCase()}` as
        | "profile.skillRadar.boxtech"
        | "profile.skillRadar.strafe"
        | "profile.skillRadar.bhop"
        | "profile.skillRadar.climb"
        | "profile.skillRadar.ladder"
        | "profile.skillRadar.slide",
    ),
  }))

  const polygon = labels
    .map((skill, index) => {
      const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2
      const pointRadius = (skill.value / 100) * radius
      const x = center + Math.cos(angle) * pointRadius
      const y = center + Math.sin(angle) * pointRadius
      return `${x},${y}`
    })
    .join(" ")

  return (
    <div className="grid gap-5">
      <div className="flex justify-center">
        <svg
          viewBox={`0 0 ${size} ${size}`}
          className="h-[220px] w-[220px] overflow-visible"
          role="img"
          aria-label={t("profile.skillRadar.ariaLabel")}
        >
          {[0.25, 0.5, 0.75, 1].map((step) => (
            <polygon
              key={step}
              points={labels
                .map((_, index) => {
                  const angle =
                    (Math.PI * 2 * index) / labels.length - Math.PI / 2
                  const x = center + Math.cos(angle) * radius * step
                  const y = center + Math.sin(angle) * radius * step
                  return `${x},${y}`
                })
                .join(" ")}
              fill="none"
              stroke="currentColor"
              className="text-border/65"
              strokeWidth="1"
            />
          ))}
          {labels.map((_, index) => {
            const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2
            const x = center + Math.cos(angle) * radius
            const y = center + Math.sin(angle) * radius
            return (
              <line
                key={index}
                x1={center}
                y1={center}
                x2={x}
                y2={y}
                stroke="currentColor"
                className="text-border/65"
                strokeWidth="1"
              />
            )
          })}
          <polygon
            points={polygon}
            fill="rgba(127,119,221,0.18)"
            stroke="rgba(127,119,221,1)"
            strokeWidth="2"
          />
          {labels.map((skill, index) => {
            const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2
            const pointRadius = (skill.value / 100) * radius
            const x = center + Math.cos(angle) * pointRadius
            const y = center + Math.sin(angle) * pointRadius
            const labelRadius = radius + 26
            const lx = center + Math.cos(angle) * labelRadius
            const ly = center + Math.sin(angle) * labelRadius
            return (
              <g key={skill.label}>
                <circle cx={x} cy={y} r="4" fill="rgba(127,119,221,1)" />
                <text
                  x={lx}
                  y={ly}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="fill-muted-foreground text-[10px] font-medium"
                >
                  {`${skill.label} ${skill.value}`}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

export function ProfileSidebar({
  identifier,
  likeMutationPending,
  onLike,
  playtimeError,
  playtimeLoading,
  playtimeSeconds,
  player,
  playerLikes,
  playerLikesError,
  playerLikesLoading,
  profileViews,
  profileViewsError,
  profileViewsLoading,
  summary,
  summaryLoading,
}: {
  identifier: string
  likeMutationPending: boolean
  onLike: () => void
  playtimeError: boolean
  playtimeLoading: boolean
  playtimeSeconds: number | null
  player: ProfilePlayer
  playerLikes: number
  playerLikesError: boolean
  playerLikesLoading: boolean
  profileViews: number
  profileViewsError: boolean
  profileViewsLoading: boolean
  summary: ProfileSummaryData
  summaryLoading: boolean
}) {
  const { t } = useTranslation()
  const authenticated = isLoggedIn()
  const navigate = useNavigate()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [socialDialogOpen, setSocialDialogOpen] = useState(false)
  const [socialTab, setSocialTab] = useState<ProfileSocialTab>("followers")
  const [identityContextMenuOpen, setIdentityContextMenuOpen] = useState(false)
  const [searchInput, setSearchInput] = useState("")
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const searchBlurTimeoutRef = useRef<number | null>(null)
  const deferredSearchInput = useDeferredValue(searchInput)
  const playerSearchQuery = deferredSearchInput.trim()
  const followSummaryQuery = useQuery(
    getProfileFollowSummaryQueryOptions(identifier),
  )
  const playerSearchQueryResult = useQuery({
    queryKey: ["graphql", "players", "search", playerSearchQuery],
    enabled: playerSearchQuery.length > 0,
    queryFn: async () =>
      (await searchPlayersGraphql(playerSearchQuery, 8)).data,
    staleTime: 30_000,
  })
  const ljPbQuery = useQuery({
    queryKey: ["profile-sidebar-lj-pb", identifier],
    queryFn: () =>
      PlayersService.readPlayerJumpstats({
        identifier,
        type: "LJ",
        limit: 1,
        offset: 0,
        sortBy: "distance",
        sortOrder: "desc",
      }),
    staleTime: 30_000,
  })
  const followSummary = followSummaryQuery.data
  const followerCount = getFollowSummaryCount(followSummary, "follower_count")
  const followingCount = getFollowSummaryCount(followSummary, "following_count")
  const viewerSteamid64 = authenticated
    ? getSteamid64FromAccessToken(localStorage.getItem("access_token"))
    : null
  const isOwnProfile =
    viewerSteamid64 === player.steamid64 ||
    user?.steamid64 === player.steamid64 ||
    followSummary?.viewer_is_self === true
  const isFollowing = followSummary?.viewer_is_following === true
  const ljPbDistance = ljPbQuery.data?.data?.[0]?.distance ?? null
  const searchResults: GraphqlPlayer[] = playerSearchQueryResult.data ?? []
  const showSearchResults = isSearchFocused && playerSearchQuery.length > 0
  const followMutation = useMutation({
    mutationFn: async () => {
      return isFollowing
        ? await PlayerFollowsService.unfollowPlayer({
            identifier: player.steamid64,
          })
        : await PlayerFollowsService.followPlayer({
            identifier: player.steamid64,
          })
    },
    onMutate: () => {
      const queryKeys = [
        ["profile-follow-summary", player.steamid64],
        ["profile-follow-summary", identifier],
      ] as const

      for (const queryKey of queryKeys) {
        queryClient.setQueryData<PlayerFollowSummaryPublic>(
          queryKey,
          (previous) => {
            if (!previous) {
              return previous
            }

            return {
              ...previous,
              follower_count: Math.max(
                0,
                (previous.follower_count ?? 0) + (isFollowing ? -1 : 1),
              ),
              viewer_is_following: !isFollowing,
            }
          },
        )
      }
    },
    onSuccess: (data) => {
      queryClient.setQueryData(
        ["profile-follow-summary", player.steamid64],
        data,
      )
      queryClient.setQueryData(["profile-follow-summary", identifier], data)
      void queryClient.invalidateQueries({
        queryKey: ["profile-follow-summary"],
      })
      void queryClient.invalidateQueries({
        queryKey: ["profile-social"],
      })
    },
    onError: () => {
      toast.error(t("profile.follow.updateFailed"))
    },
  })

  useEffect(() => {
    return () => {
      if (searchBlurTimeoutRef.current !== null) {
        window.clearTimeout(searchBlurTimeoutRef.current)
      }
    }
  }, [])

  useEffect(() => {
    setSearchInput("")
    setIsSearchFocused(false)
  }, [])

  const handleOpenSocial = (tab: ProfileSocialTab) => {
    if (!authenticated) {
      void navigate({ to: "/login" })
      return
    }

    setSocialTab(tab)
    setSocialDialogOpen(true)
  }

  const handleLikeClick = () => {
    if (isOwnProfile) {
      handleOpenSocial("likes")
      return
    }

    if (!authenticated) {
      void navigate({ to: "/login" })
      return
    }

    onLike()
  }

  const handleFollowClick = () => {
    if (isOwnProfile) {
      handleOpenSocial("followers")
      return
    }

    if (!authenticated) {
      void navigate({ to: "/login" })
      return
    }

    if (followSummaryQuery.isLoading || followMutation.isPending) {
      return
    }

    followMutation.mutate()
  }

  const handleSelectPlayer = (nextPlayer: GraphqlPlayer) => {
    setSearchInput(getPlayerDisplayName(nextPlayer))
    setIsSearchFocused(false)
    void navigate({
      to: "/profile/$identifier",
      params: {
        identifier: nextPlayer.customId?.trim() || nextPlayer.steamid64,
      },
    })
  }

  return (
    <>
      <div className="grid min-w-0 items-stretch gap-6 md:auto-rows-fr md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-1 xl:auto-rows-auto">
        <ProfileIdentityCard
          displayName={player.alias || player.name}
          profileSummary={summary}
          profileSummaryLoading={summaryLoading}
          onContextMenuOpenChange={setIdentityContextMenuOpen}
          openContextMenu={identityContextMenuOpen}
          player={player}
        />

        <Card className="h-full min-w-0 gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0">
          <CardContent className="space-y-4 p-6">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                aria-label={t("profile.searchAria")}
                value={searchInput}
                onChange={(event) => {
                  if (searchBlurTimeoutRef.current !== null) {
                    window.clearTimeout(searchBlurTimeoutRef.current)
                  }
                  setSearchInput(event.target.value)
                  setIsSearchFocused(true)
                }}
                onFocus={() => {
                  if (searchBlurTimeoutRef.current !== null) {
                    window.clearTimeout(searchBlurTimeoutRef.current)
                  }
                  setIsSearchFocused(true)
                }}
                onBlur={() => {
                  searchBlurTimeoutRef.current = window.setTimeout(() => {
                    setIsSearchFocused(false)
                  }, 100)
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && searchResults.length > 0) {
                    event.preventDefault()
                    handleSelectPlayer(searchResults[0])
                  }
                  if (event.key === "Escape") {
                    setIsSearchFocused(false)
                  }
                }}
                placeholder={t("profile.searchPlaceholder")}
                className="pr-10 pl-9"
              />
              {searchInput.length > 0 ? (
                <button
                  type="button"
                  className="absolute top-1/2 right-2 inline-flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => {
                    setSearchInput("")
                    setIsSearchFocused(false)
                  }}
                  aria-label={t("profile.clearSearch")}
                >
                  <X className="size-4" />
                </button>
              ) : null}
              {showSearchResults ? (
                <div className="absolute inset-x-0 top-[calc(100%+0.5rem)] z-20 overflow-hidden rounded-xl border border-border/70 bg-card shadow-lg">
                  {playerSearchQueryResult.isLoading ? (
                    <div className="px-4 py-3 text-sm text-muted-foreground">
                      {t("profile.searchingPlayers")}
                    </div>
                  ) : playerSearchQueryResult.isError ? (
                    <div className="px-4 py-3 text-sm text-destructive">
                      {t("profile.searchUnavailable")}
                    </div>
                  ) : searchResults.length === 0 ? (
                    <div className="px-4 py-3 text-sm text-muted-foreground">
                      {t("profile.noPlayers")}
                    </div>
                  ) : (
                    <div className="py-1">
                      {searchResults.map((nextPlayer) => (
                        <button
                          key={nextPlayer.steamid64}
                          type="button"
                          className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm transition-colors hover:bg-muted/60"
                          onMouseDown={(event) => {
                            event.preventDefault()
                            handleSelectPlayer(nextPlayer)
                          }}
                        >
                          <PlayerDisplay
                            player={nextPlayer}
                            disableProfileLink
                            className="min-w-0"
                          />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : null}
            </div>

            <div className="space-y-0.5">
              <DetailRow
                label={t("profile.summary.steamId64")}
                value={<SteamIdContextValue steamid64={player.steamid64} />}
              />
              <DetailRow
                label={t("profile.summary.dateJoined")}
                value={
                  <FormattedDateTime
                    value={player.created_at}
                    display="relative"
                    fallback={t("common.unknown")}
                  />
                }
              />
              <DetailRow
                label={t("profile.summary.lastPlayed")}
                value={
                  <FormattedDateTime
                    value={player.last_played_at}
                    display="relative"
                    fallback={t("common.unknown")}
                  />
                }
              />
              <DetailRow
                label={t("profile.summary.playtime")}
                value={
                  playtimeLoading ? (
                    <Skeleton className="h-4 w-16" />
                  ) : playtimeError ? (
                    t("profile.unavailable")
                  ) : (
                    formatSecondsAsHours(playtimeSeconds ?? 0)
                  )
                }
              />
              <DetailRow
                label={t("profile.summary.ljPb")}
                value={
                  ljPbQuery.isLoading ? (
                    <Skeleton className="h-4 w-14" />
                  ) : ljPbQuery.isError ? (
                    t("profile.unavailable")
                  ) : ljPbDistance === null ? (
                    "-"
                  ) : (
                    `${formatJumpDistance(ljPbDistance)} ${t("profile.jumpstats.units")}`
                  )
                }
              />
            </div>

            <div className="grid grid-cols-3 gap-3">
              <SummaryMiniCard
                dataTestId="profile-profile-views-card"
                icon={<Eye className="size-3.5" />}
                labelHidden
                label={t("profile.summary.profileViews")}
                value={
                  profileViewsLoading ? (
                    <Skeleton className="h-4 w-14" />
                  ) : profileViewsError ? (
                    t("profile.unavailable")
                  ) : (
                    formatNumber(profileViews)
                  )
                }
              />
              <SummaryMiniCard
                dataTestId="profile-player-likes-card"
                disabled={likeMutationPending}
                icon={<Heart className="size-3.5 fill-current" />}
                iconClassName="text-rose-500"
                labelHidden
                label={t("profile.summary.likes")}
                onClick={handleLikeClick}
                value={
                  playerLikesLoading ? (
                    <Skeleton className="h-4 w-14" />
                  ) : playerLikesError ? (
                    t("profile.unavailable")
                  ) : (
                    formatNumber(playerLikes)
                  )
                }
              />
              <SummaryMiniCard
                disabled={
                  followSummaryQuery.isLoading || followMutation.isPending
                }
                icon={
                  isOwnProfile ? (
                    <UserRoundCheck className="size-3.5" />
                  ) : isFollowing ? (
                    <UserCheck className="size-3.5" />
                  ) : (
                    <UserPlus className="size-3.5" />
                  )
                }
                labelHidden
                label={
                  isOwnProfile
                    ? t("profile.summary.followers")
                    : isFollowing
                      ? t("profile.follow.unfollow")
                      : t("profile.follow.follow")
                }
                dataTestId="profile-followers-card"
                onClick={handleFollowClick}
                value={formatNumber(followerCount)}
              />
            </div>
          </CardContent>
        </Card>

        <Card className="h-full min-w-0 gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
          <CardContent className="space-y-5 p-6">
            <div>
              <div className="flex items-center gap-2">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                  {t("profile.skillRadar.title")}
                </p>
                <Tooltip delayDuration={150}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      aria-label={t(
                        "profile.skillRadar.placeholderTooltipAria",
                      )}
                      className="inline-flex size-4 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <InfoIcon className="size-3.5" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent sideOffset={8} className="max-w-56">
                    {t("profile.skillRadar.placeholderTooltip")}
                  </TooltipContent>
                </Tooltip>
              </div>
            </div>
            <SkillRadar />
          </CardContent>
        </Card>
      </div>
      <ProfileSocialDialog
        followerCount={followerCount}
        followingCount={followingCount}
        identifier={identifier}
        likeCount={playerLikes}
        onOpenChange={setSocialDialogOpen}
        onTabChange={setSocialTab}
        open={socialDialogOpen}
        tab={socialTab}
      />
    </>
  )
}
