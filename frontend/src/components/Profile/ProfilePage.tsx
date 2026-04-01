import { Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import {
  BarChart3,
  Trophy,
} from "lucide-react"
import { type ReactNode, useMemo, useState } from "react"

import { type PlayerPublic, PlayersService } from "@/client"
import { CountryFlag } from "@/components/Common/CountryFlag"
import ErrorComponent from "@/components/Common/ErrorComponent"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import NotFound from "@/components/Common/NotFound"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { getInitials } from "@/utils"

import {
  type ProfileActivityYear,
  profileHomePlaceholder,
} from "./profile-home-placeholder"

type ProfileTab = "home" | "records" | "stats"

const tabDefinitions: Array<{
  key: ProfileTab
  label: string
  to: "/profile/$steamid64" | "/profile/$steamid64/records" | "/profile/$steamid64/stats"
}> = [
  { key: "home", label: "Home", to: "/profile/$steamid64" },
  { key: "records", label: "Records", to: "/profile/$steamid64/records" },
  { key: "stats", label: "Stats", to: "/profile/$steamid64/stats" },
]

const activityTones = [
  "bg-muted/70",
  "bg-primary/15",
  "bg-primary/30",
  "bg-primary/55",
  "bg-primary",
]

const badgeToneClasses: Record<string, string> = {
  amber:
    "border-amber-300/70 bg-amber-100 text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-200",
  emerald:
    "border-emerald-300/70 bg-emerald-100 text-emerald-900 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-200",
  orange:
    "border-orange-300/70 bg-orange-100 text-orange-900 dark:border-orange-500/40 dark:bg-orange-500/15 dark:text-orange-200",
  sky: "border-sky-300/70 bg-sky-100 text-sky-900 dark:border-sky-500/40 dark:bg-sky-500/15 dark:text-sky-200",
  stone:
    "border-stone-300/70 bg-stone-100 text-stone-900 dark:border-stone-500/40 dark:bg-stone-500/15 dark:text-stone-200",
  violet:
    "border-violet-300/70 bg-violet-100 text-violet-900 dark:border-violet-500/40 dark:bg-violet-500/15 dark:text-violet-200",
}

function isValidSteamid64(steamid64: string) {
  return /^\d{17}$/.test(steamid64)
}

async function fetchProfilePlayer(steamid64: string) {
  const response = await PlayersService.readPlayersBatch({
    requestBody: { steamid64s: [steamid64] },
  })

  return response.data[0] ?? null
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value)
}

function formatHours(hours: number) {
  return `${formatNumber(hours)} hrs`
}

function formatCompactPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

function formatRatingBadge(value: number) {
  return (value / 1158).toFixed(2)
}

function getAvatarUrl(player: PlayerPublic) {
  if (!player.avatar_hash) {
    return null
  }

  return `https://avatars.steamstatic.com/${player.avatar_hash}_full.jpg`
}

function ProfileSkeleton() {
  return (
    <div className="space-y-8">
      <Skeleton className="h-56 rounded-[28px]" />
      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Skeleton className="h-[680px] rounded-[28px]" />
        <div className="space-y-6">
          <Skeleton className="h-48 rounded-[28px]" />
          <Skeleton className="h-64 rounded-[28px]" />
          <Skeleton className="h-80 rounded-[28px]" />
        </div>
      </div>
    </div>
  )
}

function ProfileTabs({
  activeTab,
  steamid64,
}: {
  activeTab: ProfileTab
  steamid64: string
}) {
  return (
    <Tabs value={activeTab} className="flex flex-col gap-4">
      <TabsList className="w-fit border border-border bg-background/60">
        {tabDefinitions.map((tab) => (
          <TabsTrigger key={tab.key} value={tab.key} asChild>
            <Link to={tab.to} params={{ steamid64 }}>
              {tab.label}
            </Link>
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}

function ProfileIdentityCard({ player }: { player: PlayerPublic }) {
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
          </div>
        </div>

      </CardContent>
    </Card>
  )
}

function DetailRow({
  label,
  value,
}: {
  label: string
  value: ReactNode
}) {
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
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="rounded-[16px] border border-border/70 bg-background/65 px-3 py-2.5">
      <p className="text-lg font-semibold tracking-tight">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
    </div>
  )
}

function MainSummaryCard({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="rounded-[20px] border border-border/70 bg-background/65 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
    </div>
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
              badgeToneClasses[skill.tone],
            )}
          >
            {skill.label} {skill.value}
          </span>
        ))}
      </div>
    </div>
  )
}

function CompletionCard({
  title,
  completed,
  total,
  tiers,
}: {
  title: string
  completed: number
  total: number
  tiers: Array<{
    label: string
    complete: number
    total: number
    color: string
  }>
}) {
  return (
    <Card className="gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              {title}
            </p>
            <p className="mt-3 text-3xl font-semibold tracking-tight">
              {formatCompactPercent(completed / total)}
            </p>
          </div>
          <p className="text-sm text-muted-foreground">
            {formatNumber(completed)} / {formatNumber(total)}
          </p>
        </div>
        <div className="space-y-1.5">
          {tiers.map((tier) => {
            const width = `${(tier.complete / tier.total) * 100}%`
            return (
              <div key={tier.label} className="grid grid-cols-[38px_minmax(0,1fr)_68px] items-center gap-3">
                <span className="text-xs font-semibold text-muted-foreground">
                  {tier.label}
                </span>
                <div className="h-5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full"
                    style={{ width, backgroundColor: tier.color }}
                  />
                </div>
                <span className="text-right font-mono text-xs text-muted-foreground">
                  {tier.complete}/{tier.total}
                </span>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

function ActivityCard() {
  const [activeYear, setActiveYear] = useState<ProfileActivityYear>("2026")
  const levels = profileHomePlaceholder.activity[activeYear]

  const weeks = useMemo(() => {
    return Array.from({ length: 53 }, (_, weekIndex) =>
      Array.from({ length: 7 }, (_, dayIndex) => levels[weekIndex * 7 + dayIndex]),
    )
  }, [levels])

  return (
    <Card className="gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Activity
            </p>
          </div>
          <div className="inline-flex rounded-full border border-border/70 bg-background/75 p-1">
            {(["2025", "2026"] as const).map((year) => (
              <button
                key={year}
                type="button"
                onClick={() => setActiveYear(year)}
                className={cn(
                  "rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                  activeYear === year
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )}
              >
                {year}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <div className="min-w-[720px] space-y-1.5">
            {Array.from({ length: 7 }, (_, rowIndex) => (
              <div key={rowIndex} className="flex gap-1.5">
                {weeks.map((week, weekIndex) => (
                  <span
                    key={`${weekIndex}-${rowIndex}`}
                    className={cn(
                      "h-3 w-3 shrink-0 rounded-[4px] border border-black/0",
                      activityTones[week[rowIndex]],
                    )}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <span>Less</span>
          {activityTones.map((tone, index) => (
            <span
              key={index}
              className={cn("h-3 w-3 rounded-[4px]", tone)}
            />
          ))}
          <span>More</span>
        </div>
      </CardContent>
    </Card>
  )
}

function PinnedRecordsCard() {
  return (
    <Card className="gap-0 rounded-[26px] border-border/70 bg-card/95 py-0">
      <CardContent className="space-y-5 p-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Pinned records
            </p>
          </div>
          <p className="text-sm text-muted-foreground">
            {profileHomePlaceholder.pinnedRecords.length} of 6
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {profileHomePlaceholder.pinnedRecords.map((record) => (
            <div
              key={`${record.map}-${record.time}`}
              className="group rounded-[22px] border border-border/70 bg-background/75 p-4 transition-colors hover:border-primary/35"
            >
              <p className="truncate text-sm font-semibold">{record.map}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {record.mode} · {record.variant} · {record.rank}
              </p>
              <p className="mt-4 text-2xl font-semibold tracking-tight text-primary">
                {record.time}
              </p>
              <div className="mt-3 flex items-center gap-2">
                <span
                  className={cn(
                    "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium",
                    badgeToneClasses[record.badgeTone],
                  )}
                >
                  {record.badge}
                </span>
                <span className="text-xs text-muted-foreground">
                  {record.achievedOn}
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function PlaceholderPanel({
  player,
  activeTab,
}: {
  player: PlayerPublic
  activeTab: Exclude<ProfileTab, "home">
}) {
  return (
    <Card className="gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
      <CardContent className="grid gap-6 px-6 py-8 md:px-8 md:py-10">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary">
          {activeTab === "records" ? <Trophy /> : <BarChart3 />}
        </div>
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            Coming soon
          </p>
          <h2 className="text-3xl font-semibold tracking-tight">
            {activeTab === "records" ? "Records" : "Stats"} for{" "}
            {player.alias || player.name}
          </h2>
          <p className="max-w-2xl text-sm text-muted-foreground">
            The route is live and public, but the content is intentionally
            minimal for this first pass. The shared profile shell and URL
            structure are now in place for future backend-backed tabs.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

export function ProfilePage({
  steamid64,
  activeTab,
}: {
  steamid64: string
  activeTab: ProfileTab
}) {
  const isValid = isValidSteamid64(steamid64)
  const playerQuery = useQuery({
    queryKey: ["profile-player", steamid64],
    queryFn: () => fetchProfilePlayer(steamid64),
    enabled: isValid,
    retry: false,
  })

  if (!isValid) {
    return <NotFound />
  }

  if (playerQuery.isLoading) {
    return <ProfileSkeleton />
  }

  if (playerQuery.isError) {
    return <ErrorComponent />
  }

  if (!playerQuery.data) {
    return <NotFound />
  }

  const player = playerQuery.data
  const placeholder = profileHomePlaceholder

  return (
    <div className="space-y-8">
      <ProfileTabs activeTab={activeTab} steamid64={steamid64} />

      {activeTab === "home" ? (
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-6">
            <ProfileIdentityCard player={player} />

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
                    value={formatHours(placeholder.summary.playtimeHours)}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <SummaryMiniCard
                    label="Views"
                    value={formatNumber(placeholder.summary.profileViews)}
                  />
                  <SummaryMiniCard
                    label="Followers"
                    value={formatNumber(placeholder.summary.likes)}
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
          </aside>

          <section className="space-y-6">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <MainSummaryCard
                label="Total Points"
                value={formatNumber(placeholder.summary.points)}
              />
              <MainSummaryCard
                label="Rank"
                value={placeholder.summary.ratingTier}
              />
              <MainSummaryCard
                label="Global Standing"
                value={`#${formatNumber(placeholder.summary.globalRank)}`}
              />
            </div>

            <div className="grid gap-6 2xl:grid-cols-2">
              <CompletionCard
                title="Overall completion"
                completed={placeholder.completion.overall.completed}
                total={placeholder.completion.overall.total}
                tiers={placeholder.completion.overall.tiers}
              />
              <CompletionCard
                title="Pro completion"
                completed={placeholder.completion.pro.completed}
                total={placeholder.completion.pro.total}
                tiers={placeholder.completion.pro.tiers}
              />
            </div>

            <ActivityCard />
            <PinnedRecordsCard />
          </section>
        </div>
      ) : (
        <PlaceholderPanel
          player={player}
          activeTab={activeTab as Exclude<ProfileTab, "home">}
        />
      )}
    </div>
  )
}
