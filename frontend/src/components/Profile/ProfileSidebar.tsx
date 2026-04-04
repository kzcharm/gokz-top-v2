import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import type { ReactNode } from "react"
import { useState } from "react"

import { ApiError, type PlayerPublic, PlayersService } from "@/client"
import { CountryFlag } from "@/components/Common/CountryFlag"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { Card, CardContent } from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { getSteamid64FromAccessToken } from "@/lib/auth"
import { cn } from "@/lib/utils"
import { getInitials } from "@/utils"

import {
  ProfileSocialDialog,
  type ProfileSocialTab,
} from "./ProfileSocialDialog"
import { profileHomePlaceholder } from "./profile-home-placeholder"
import {
  formatHours,
  formatNumber,
  formatRatingBadge,
  getAvatarUrl,
  getFollowButtonLabel,
  getFollowSummaryCount,
  getProfileFollowSummaryQueryOptions,
  profileBadgeToneClasses,
} from "./profile-utils"

function ProfileIdentityCard({
  buttonLabel,
  followDisabled,
  isFollowing,
  followLoading,
  onFollowClick,
  player,
  showFollowButton,
}: {
  buttonLabel: string
  followDisabled: boolean
  isFollowing: boolean
  followLoading: boolean
  onFollowClick: () => void
  player: PlayerPublic
  showFollowButton: boolean
}) {
  const avatarUrl = getAvatarUrl(player)
  const summary = profileHomePlaceholder.summary

  return (
    <Card className="gap-0 overflow-hidden rounded-[28px] border-border/70 bg-card/95 py-0">
      <CardContent className="relative space-y-6 p-6">
        <div className="absolute inset-x-0 top-0 h-40 bg-[radial-gradient(circle_at_top_left,rgba(127,119,221,0.2),transparent_42%),radial-gradient(circle_at_75%_20%,rgba(29,158,117,0.16),transparent_28%)]" />

        <div className="relative flex flex-col items-center gap-4 text-center">
          <div className="relative">
            <div className="absolute -inset-2 rounded-[28px] bg-[radial-gradient(circle,rgba(127,119,221,0.28),transparent_72%)] blur-2xl" />
            <div className="relative flex h-24 w-24 items-center justify-center overflow-hidden rounded-[24px] border border-white/40 bg-gradient-to-br from-primary via-primary/85 to-emerald-500/85 shadow-lg shadow-primary/15">
              {avatarUrl ? (
                <img
                  src={avatarUrl}
                  alt={`${player.name} avatar`}
                  className="h-full w-full object-cover"
                />
              ) : (
                <span className="text-3xl font-semibold text-white">
                  {getInitials(player.alias || player.name)}
                </span>
              )}
              <span className="absolute bottom-2 right-2 h-3.5 w-3.5 rounded-full border-2 border-card bg-emerald-500" />
            </div>
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
                <h1 className="text-3xl font-semibold tracking-tight">
                  {player.alias || player.name}
                </h1>
              </div>
              <p className="text-sm text-muted-foreground">{player.name}</p>
            </div>

            <div className="flex flex-wrap justify-center gap-2 pt-2">
              <span className="inline-flex items-center rounded-full border border-border/70 bg-background/80 px-3 py-1 text-xs font-semibold text-foreground">
                Rating {formatRatingBadge(summary.rating)}
              </span>
              <span className="inline-flex items-center rounded-full border border-border/70 bg-background/80 px-3 py-1 text-xs font-semibold text-foreground">
                Global #{formatNumber(summary.globalRank)}
              </span>
              <span className="inline-flex items-center rounded-full border border-border/70 bg-background/80 px-3 py-1 text-xs font-semibold text-foreground">
                EU #{formatNumber(summary.regionalRank)}
              </span>
            </div>

            {showFollowButton ? (
              <LoadingButton
                type="button"
                variant={isFollowing ? "outline" : "default"}
                className="min-w-40 rounded-full"
                data-testid="profile-follow-button"
                disabled={followDisabled}
                loading={followLoading}
                onClick={onFollowClick}
              >
                {buttonLabel}
              </LoadingButton>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5 text-sm">
      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </span>
      <span className="text-right text-sm font-semibold">{value}</span>
    </div>
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
  const size = 220
  const center = size / 2
  const radius = 74
  const labels = profileHomePlaceholder.skills

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
          aria-label="Placeholder skill radar"
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
            const labelRadius = radius + 22
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
                  className="fill-muted-foreground text-[11px] font-medium"
                >
                  {skill.label}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {labels.map((skill) => (
          <span
            key={skill.label}
            className={cn(
              "inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium",
              profileBadgeToneClasses[skill.tone],
            )}
          >
            {skill.label} {skill.value}
          </span>
        ))}
      </div>
    </div>
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

export function ProfileSidebar({
  identifier,
  player,
}: {
  identifier: string
  player: PlayerPublic
}) {
  const summary = profileHomePlaceholder.summary
  const authenticated = isLoggedIn()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { showErrorToast } = useCustomToast()
  const [socialDialogOpen, setSocialDialogOpen] = useState(false)
  const [socialTab, setSocialTab] = useState<ProfileSocialTab>("followers")
  const viewerSteamid64 = authenticated
    ? getSteamid64FromAccessToken(localStorage.getItem("access_token"))
    : null
  const followSummaryQuery = useQuery(
    getProfileFollowSummaryQueryOptions(identifier),
  )
  const followSummary = followSummaryQuery.data
  const isOwnProfile =
    viewerSteamid64 === player.steamid64 ||
    user?.steamid64 === player.steamid64 ||
    followSummary?.viewer_is_self === true
  const isFollowing = followSummary?.viewer_is_following === true
  const followerCount = getFollowSummaryCount(followSummary, "follower_count")
  const followingCount = getFollowSummaryCount(followSummary, "following_count")
  const followButtonLabel = getFollowButtonLabel({
    authenticated,
    isFollowing,
  })
  const followMutation = useMutation({
    mutationFn: async () => {
      return isFollowing
        ? await PlayersService.unfollowPlayer({ identifier })
        : await PlayersService.followPlayer({ identifier })
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["profile-follow-summary", identifier], data)
      void queryClient.invalidateQueries({
        queryKey: ["profile-social", "followers", identifier],
      })
      void queryClient.invalidateQueries({
        queryKey: ["profile-social", "following", identifier],
      })
    },
    onError: (error) => {
      showErrorToast(getApiErrorMessage(error))
    },
  })

  const handleFollowClick = () => {
    if (!authenticated) {
      void navigate({ to: "/login" })
      return
    }
    if (isOwnProfile || followMutation.isPending) {
      return
    }

    followMutation.mutate()
  }

  const handleOpenSocial = (tab: ProfileSocialTab) => {
    if (!authenticated) {
      void navigate({ to: "/login" })
      return
    }

    setSocialTab(tab)
    setSocialDialogOpen(true)
  }

  return (
    <div className="space-y-6">
      <ProfileIdentityCard
        buttonLabel={followButtonLabel}
        followDisabled={
          authenticated &&
          (!followSummary ||
            followSummaryQuery.isLoading ||
            followMutation.isPending)
        }
        isFollowing={isFollowing}
        followLoading={followMutation.isPending}
        onFollowClick={handleFollowClick}
        player={player}
        showFollowButton={!isOwnProfile}
      />

      <Card className="gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="space-y-4 p-6">
          <div className="space-y-0.5">
            <DetailRow label="SteamID64" value={player.steamid64} />
            <DetailRow
              label="Date Joined"
              value={
                <FormattedDateTime
                  value={player.created_at}
                  display="relative"
                  fallback="Unknown"
                />
              }
            />
            <DetailRow
              label="Last Played"
              value={
                <FormattedDateTime
                  value={player.last_played_at}
                  display="relative"
                  fallback="Unknown"
                />
              }
            />
            <DetailRow
              label="Playtime"
              value={formatHours(summary.playtimeHours)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <SummaryMiniCard
              dataTestId="profile-profile-views-card"
              label="Profile Views"
              value={formatNumber(player.profile_views ?? 0)}
            />
            <SummaryMiniCard
              label="Followers"
              dataTestId="profile-followers-card"
              onClick={() => handleOpenSocial("followers")}
              value={formatNumber(followerCount)}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="space-y-5 p-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Skill radar
            </p>
          </div>
          <SkillRadar />
        </CardContent>
      </Card>

      <ProfileSocialDialog
        followerCount={followerCount}
        followingCount={followingCount}
        identifier={identifier}
        onOpenChange={setSocialDialogOpen}
        onTabChange={setSocialTab}
        open={socialDialogOpen}
        tab={socialTab}
      />
    </div>
  )
}
