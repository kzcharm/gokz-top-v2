import { useQuery } from "@tanstack/react-query"

import {
  PlayersService,
  type TournamentAchievementPublic,
  type TournamentLevel,
} from "@/client"
import {
  TROPHY_ASSETS,
  type TrophyAsset,
} from "@/components/Common/trophy-assets"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

const LEVEL_BADGE_CLASS_NAMES: Record<TournamentLevel, string> = {
  S: "border-[#FF0000]/70 bg-[#FF0000]/20 text-red-950 dark:text-[#FF8080]",
  A: "border-[#CC99FF]/70 bg-[#CC99FF]/20 text-purple-950 dark:text-[#CC99FF]",
  B: "border-[#99CCFF]/70 bg-[#99CCFF]/20 text-sky-950 dark:text-[#99CCFF]",
  C: "border-border/70 bg-background/80 text-foreground",
}

const PLACEMENT_DETAILS = {
  1: { label: "Champion", trophy: "gold" },
  2: { label: "Runner-up", trophy: "silver" },
  3: { label: "Third Place", trophy: "bronze" },
  4: { label: "Semifinalist", trophy: "bronze" },
} as const

function formatTournamentDates(achievement: TournamentAchievementPublic) {
  const { ends_on, starts_on } = achievement.tournament
  return starts_on === ends_on ? starts_on : `${starts_on} – ${ends_on}`
}

function TournamentAchievementBadge({
  achievement,
}: {
  achievement: TournamentAchievementPublic
}) {
  const placement =
    PLACEMENT_DETAILS[achievement.placement as keyof typeof PLACEMENT_DETAILS]
  const content = (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-semibold",
        LEVEL_BADGE_CLASS_NAMES[achievement.tournament.level],
      )}
    >
      <span>{achievement.tournament.name}</span>
      <img
        aria-hidden="true"
        alt=""
        className="size-4 object-contain"
        src={TROPHY_ASSETS[placement.trophy as TrophyAsset]}
      />
      <span className="sr-only">{placement.label}</span>
    </span>
  )

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {achievement.tournament.official_url ? (
          <a
            href={achievement.tournament.official_url}
            target="_blank"
            rel="noreferrer"
            className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {content}
          </a>
        ) : (
          content
        )}
      </TooltipTrigger>
      <TooltipContent>
        <p>{placement.label}</p>
        <p className="text-muted-foreground">
          Level {achievement.tournament.level} ·{" "}
          {formatTournamentDates(achievement)}
        </p>
      </TooltipContent>
    </Tooltip>
  )
}

export function ProfileTournamentAchievements({
  steamid64,
}: {
  steamid64: string
}) {
  const achievementsQuery = useQuery({
    queryKey: ["player-tournament-achievements", steamid64],
    queryFn: () =>
      PlayersService.readPlayerTournamentAchievements({
        identifier: steamid64,
      }),
    staleTime: 60_000,
  })
  const achievements = achievementsQuery.data?.data ?? []

  if (achievements.length === 0) {
    return null
  }

  return (
    <span className="contents" data-testid="profile-tournament-achievements">
      {achievements.map((achievement) => (
        <TournamentAchievementBadge
          key={achievement.id}
          achievement={achievement}
        />
      ))}
    </span>
  )
}
