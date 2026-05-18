import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Copy, History, Search, X } from "lucide-react"
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

import { type PlayerPublic, PlayersService } from "@/client"
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
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog"
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
import { type GraphqlPlayer, searchPlayersGraphql } from "@/lib/player-graphql"
import { getSocialPlatformLabel, SocialPlatformIcon } from "@/lib/social-links"
import { isSuperuser } from "@/lib/user-roles"
import { cn } from "@/lib/utils"
import { getInitials } from "@/utils"

import { ProfileHistoryDialog } from "./ProfileHistoryDialog"
import {
  ProfileSocialDialog,
  type ProfileSocialTab,
} from "./ProfileSocialDialog"
import { profileHomePlaceholder } from "./profile-home-placeholder"
import {
  formatNumber,
  formatRating,
  formatSecondsAsHours,
  getAvatarUrl,
  getFollowSummaryCount,
  getProfileFollowSummaryQueryOptions,
  type ProfileSummaryData,
} from "./profile-utils"

type ProfilePlayer = PlayerPublic & {
  is_website_user?: boolean
}

function formatJumpDistance(value: number) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function ProfileIdentityCard({
  canViewProfileHistory,
  displayName,
  onOpenProfileHistory,
  profileSummary,
  profileSummaryLoading,
  onContextMenuOpenChange,
  openContextMenu,
  player,
}: {
  canViewProfileHistory: boolean
  displayName: string
  onOpenProfileHistory: () => void
  profileSummary: ProfileSummaryData
  profileSummaryLoading: boolean
  onContextMenuOpenChange: (open: boolean) => void
  openContextMenu: boolean
  player: ProfilePlayer
}) {
  const { t } = useTranslation()
  const [addBanDialogOpen, setAddBanDialogOpen] = useState(false)
  const avatarUrl = getAvatarUrl(player)
  const showWebsiteUserRing = player.is_website_user === true
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
      PlayersService.readPlayerSocialLinks({
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
                        showWebsiteUserRing
                          ? `profile-avatar-ring-${player.steamid64}`
                          : undefined
                      }
                      className={cn(
                        "relative flex h-32 w-32 cursor-zoom-in items-center justify-center overflow-hidden rounded-[28px] border border-white/40 bg-gradient-to-br from-primary via-primary/85 to-emerald-500/85 shadow-lg shadow-primary/15 transition-transform hover:scale-[1.02] focus-visible:outline-none",
                        showWebsiteUserRing &&
                          "ring-4 ring-pink-400/90 ring-offset-4 ring-offset-card",
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
              <span className="inline-flex items-center rounded-full border border-border/70 bg-background/80 px-3 py-1 text-xs font-semibold text-foreground">
                {profileSummaryLoading
                  ? `${t("labels.points")} ...`
                  : `${profileSummary.rankLabel} ${formatNumber(profileSummary.totalPoints)}`}
              </span>
              <span className="inline-flex items-center rounded-full border border-border/70 bg-background/80 px-3 py-1 text-xs font-semibold text-foreground">
                {t("profile.summary.rating")}{" "}
                {profileSummaryLoading
                  ? "..."
                  : profileSummary.rating === null
                    ? t("profile.unranked")
                    : formatRating(profileSummary.rating)}
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
          onAddBan={() => setAddBanDialogOpen(true)}
          player={player}
          steamProfileUrl={steamProfileUrl}
          steamid64={player.steamid64}
        >
          {canViewProfileHistory ? (
            <DropdownMenuItem
              data-testid="profile-history-menu-item"
              onSelect={onOpenProfileHistory}
            >
              <History />
              {t("profile.history.menuAction")}
            </DropdownMenuItem>
          ) : null}
          <PlayerFollowContextMenuItem
            menuOpen={openContextMenu}
            steamid64={player.steamid64}
            testId="profile-follow-menu-item"
          />
        </PlayerContextMenuItems>
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
  label,
  onClick,
  value,
}: {
  dataTestId?: string
  label: string
  onClick?: () => void
  value: string
}) {
  const Comp = onClick ? "button" : "div"

  return (
    <Comp
      className={cn(
        "rounded-[16px] border border-border/70 bg-background/65 px-3 py-2.5 text-left transition-colors",
        onClick
          ? "cursor-pointer hover:bg-background/90 focus-visible:bg-background/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          : "",
      )}
      data-testid={dataTestId}
      onClick={onClick}
      type={onClick ? "button" : undefined}
    >
      <p className="text-lg font-semibold tracking-tight">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
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
        | "profile.skillRadar.route"
        | "profile.skillRadar.strafe"
        | "profile.skillRadar.bhop"
        | "profile.skillRadar.micro"
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
  playtimeError,
  playtimeLoading,
  playtimeSeconds,
  player,
  summary,
  summaryLoading,
}: {
  identifier: string
  playtimeError: boolean
  playtimeLoading: boolean
  playtimeSeconds: number | null
  player: ProfilePlayer
  summary: ProfileSummaryData
  summaryLoading: boolean
}) {
  const { t } = useTranslation()
  const authenticated = isLoggedIn()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false)
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
  const ljPbDistance = ljPbQuery.data?.data?.[0]?.distance ?? null
  const canViewProfileHistory = isSuperuser(user)
  const searchResults: GraphqlPlayer[] = playerSearchQueryResult.data ?? []
  const showSearchResults = isSearchFocused && playerSearchQuery.length > 0

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
          canViewProfileHistory={canViewProfileHistory}
          displayName={player.alias || player.name}
          onOpenProfileHistory={() => {
            setHistoryDialogOpen(true)
          }}
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
                    formatJumpDistance(ljPbDistance)
                  )
                }
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <SummaryMiniCard
                dataTestId="profile-profile-views-card"
                label={t("profile.summary.profileViews")}
                value={formatNumber(player.profile_views ?? 0)}
              />
              <SummaryMiniCard
                label={t("profile.summary.followers")}
                dataTestId="profile-followers-card"
                onClick={() => handleOpenSocial("followers")}
                value={formatNumber(followerCount)}
              />
            </div>
          </CardContent>
        </Card>

        <Card className="h-full min-w-0 gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
          <CardContent className="space-y-5 p-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                {t("profile.skillRadar.title")}
              </p>
            </div>
            <SkillRadar />
          </CardContent>
        </Card>
      </div>
      <ProfileHistoryDialog
        identifier={identifier}
        onOpenChange={setHistoryDialogOpen}
        open={historyDialogOpen}
      />
      <ProfileSocialDialog
        followerCount={followerCount}
        followingCount={followingCount}
        identifier={identifier}
        onOpenChange={setSocialDialogOpen}
        onTabChange={setSocialTab}
        open={socialDialogOpen}
        tab={socialTab}
      />
    </>
  )
}
