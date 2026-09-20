import type { ColumnDef } from "@tanstack/react-table"
import type { TFunction } from "i18next"
import { ArrowDown, ChevronDown } from "lucide-react"

import type { ModeScope, PlayerLeaderboardEntryPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import {
  PlayerDisplay,
  type PlayerDisplayPlayer,
} from "@/components/Common/PlayerDisplay"
import { formatRating } from "@/components/Profile/profile-utils"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { formatNumber } from "@/i18n/locale"

export type LeaderboardTableRow = PlayerLeaderboardEntryPublic & {
  playerData: PlayerDisplayPlayer
}

export type LeaderboardSkill =
  | "boxtech"
  | "strafe"
  | "bhop"
  | "climb"
  | "ladder"
  | "slide"

const LEADERBOARD_SKILLS: ReadonlyArray<{
  color: string
  key: LeaderboardSkill
}> = [
  { color: "#b83280", key: "boxtech" },
  { color: "#d64545", key: "strafe" },
  { color: "#229ac2", key: "bhop" },
  { color: "#26965c", key: "climb" },
  { color: "#e57d2b", key: "ladder" },
  { color: "#776ba5", key: "slide" },
]

function formatMetric(value: number) {
  return formatNumber(value)
}

function formatLeaderboardMetric(
  accessorKey: keyof PlayerLeaderboardEntryPublic,
  value: number | null,
) {
  if (
    accessorKey === "rating" ||
    accessorKey === "rating_easy" ||
    accessorKey === "rating_hard"
  ) {
    if (value === null) {
      return "0.00"
    }
    return formatRating(value)
  }

  if (value === null) {
    return "0"
  }
  return formatMetric(value)
}

function formatRawRating(value: number | null) {
  if (value === null) {
    return "No raw rating"
  }

  return formatMetric(value)
}

function skillLabel(t: TFunction, skill: LeaderboardSkill) {
  return t(`profile.skillRadar.${skill}`)
}

function SkillHeader({
  column,
  selectedSkill,
  t,
  onSkillChange,
}: {
  column: {
    getIsSorted: () => false | "asc" | "desc"
  }
  selectedSkill: LeaderboardSkill
  t: TFunction
  onSkillChange: (skill: LeaderboardSkill) => void
}) {
  const selectedOption = LEADERBOARD_SKILLS.find(
    (skill) => skill.key === selectedSkill,
  )!
  const selectedLabel = skillLabel(t, selectedSkill)

  return (
    <div className="flex w-full justify-center">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            className="h-8 px-3"
            aria-label={t("leaderboards.players.skills.select", {
              skill: selectedLabel,
            })}
          >
            <span
              aria-hidden="true"
              className="size-2.5 rounded-full"
              style={{ backgroundColor: selectedOption.color }}
            />
            {selectedLabel}
            {column.getIsSorted() ? (
              <ArrowDown className="ml-1 size-4" />
            ) : (
              <ChevronDown className="ml-1 size-4 text-muted-foreground" />
            )}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="center" className="min-w-36">
          <DropdownMenuRadioGroup value={selectedSkill}>
            {LEADERBOARD_SKILLS.map((skill) => (
              <DropdownMenuRadioItem
                key={skill.key}
                value={skill.key}
                onSelect={() => onSkillChange(skill.key)}
              >
                <span
                  aria-hidden="true"
                  className="size-2.5 rounded-full"
                  data-skill-color={skill.key}
                  style={{ backgroundColor: skill.color }}
                />
                {skillLabel(t, skill.key)}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

function skillColumn(
  t: TFunction,
  selectedSkill: LeaderboardSkill,
  onSkillChange: (skill: LeaderboardSkill) => void,
): ColumnDef<LeaderboardTableRow> {
  return {
    id: `rating_${selectedSkill}`,
    size: 92,
    accessorFn: (row) => row.skill_ratings?.[selectedSkill]?.raw_rating ?? 0,
    header: ({ column }) => (
      <SkillHeader
        column={column}
        selectedSkill={selectedSkill}
        t={t}
        onSkillChange={onSkillChange}
      />
    ),
    cell: ({ row }) => {
      const skillRating = row.original.skill_ratings?.[selectedSkill]
      const displayRating = skillRating?.rating

      return (
        <div className="flex w-full justify-center">
          {displayRating == null ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            <Tooltip delayDuration={250}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className="rounded-sm bg-transparent p-0 font-medium tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                >
                  {formatRating(displayRating)}
                </button>
              </TooltipTrigger>
              <TooltipContent sideOffset={6}>
                {t("leaderboards.players.skills.rawRating", {
                  rating: formatRawRating(skillRating?.raw_rating ?? null),
                })}
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      )
    },
  }
}

export function SortableHeader({
  title,
  column,
  align = "center",
}: {
  title: string
  column: {
    getIsSorted: () => false | "asc" | "desc"
    toggleSorting: (desc?: boolean) => void
  }
  align?: "center" | "right"
}) {
  const sorting = column.getIsSorted()
  const containerClassName =
    align === "right" ? "flex w-full justify-end" : "flex w-full justify-center"
  const buttonClassName = align === "right" ? "h-8 px-3" : "h-8 px-3"

  return (
    <div className={containerClassName}>
      <Button
        type="button"
        variant="ghost"
        className={buttonClassName}
        onClick={() => column.toggleSorting(true)}
      >
        {title}
        {sorting ? <ArrowDown className="ml-2 size-4" /> : null}
      </Button>
    </div>
  )
}

function metricColumn(
  accessorKey:
    | "rating"
    | "rating_easy"
    | "rating_hard"
    | "points"
    | "wrs_nub"
    | "wrs_pro"
    | "records_900_plus"
    | "records_800_plus"
    | "unique_map_finishes",
  title: () => string,
  align: "center" | "right" = "center",
): ColumnDef<LeaderboardTableRow> {
  const size =
    accessorKey === "points"
      ? 92
      : accessorKey === "unique_map_finishes"
        ? 68
        : 80

  return {
    accessorKey,
    size,
    header: ({ column }) => (
      <SortableHeader title={title()} column={column} align={align} />
    ),
    cell: ({ row }) => (
      <div
        className={
          align === "right"
            ? "flex w-full justify-end"
            : "flex w-full justify-center"
        }
      >
        {accessorKey === "rating" ? (
          <Tooltip delayDuration={250}>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="rounded-sm bg-transparent p-0 font-medium tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              >
                {formatLeaderboardMetric(
                  accessorKey,
                  row.original[accessorKey],
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent sideOffset={6}>
              Raw rating: {formatRawRating(row.original.raw_rating)}
            </TooltipContent>
          </Tooltip>
        ) : (
          <span className="font-medium tabular-nums">
            {formatLeaderboardMetric(accessorKey, row.original[accessorKey])}
          </span>
        )}
      </div>
    ),
  }
}

export function getLeaderboardColumns(
  t: TFunction,
  scope?: ModeScope,
  friendsOnly = false,
  selectedSkill: LeaderboardSkill = "climb",
  onSkillChange: (skill: LeaderboardSkill) => void = () => {},
): ColumnDef<LeaderboardTableRow>[] {
  return [
    {
      accessorKey: "rank",
      size: friendsOnly ? 92 : 48,
      header: () => <div className="flex w-full justify-center">#</div>,
      cell: ({ row }) => {
        const globalRank =
          typeof row.original.global_rank === "number"
            ? row.original.global_rank
            : null

        return (
          <div className="flex w-full justify-center">
            {friendsOnly && globalRank !== null ? (
              <span className="font-semibold tabular-nums">
                {formatMetric(row.original.rank)}{" "}
                <span className="text-muted-foreground">
                  ({formatMetric(globalRank)})
                </span>
              </span>
            ) : (
              <span className="font-semibold tabular-nums">
                {formatMetric(row.original.rank)}
              </span>
            )}
          </div>
        )
      },
    },
    {
      accessorKey: "player",
      size: 180,
      header: () => t("labels.player"),
      cell: ({ row }) => (
        <PlayerDisplay player={row.original.playerData} scope={scope} />
      ),
    },
    metricColumn("rating", () => "Rating"),
    metricColumn("rating_easy", () => "Rating.E"),
    metricColumn("rating_hard", () => "Rating.H"),
    skillColumn(t, selectedSkill, onSkillChange),
    metricColumn("points", () => t("labels.points"), "right"),
    metricColumn("wrs_nub", () => "NUB WRs"),
    metricColumn("wrs_pro", () => "PRO WRs"),
    metricColumn("records_900_plus", () => "900+"),
    metricColumn("records_800_plus", () => "800+"),
    metricColumn("unique_map_finishes", () => t("labels.maps")),
    {
      id: "last_played",
      size: 88,
      header: () => (
        <div className="flex w-full justify-center">
          {t("labels.lastPlayed")}
        </div>
      ),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex w-full justify-center">
          <FormattedDateTime
            className="text-muted-foreground"
            value={row.original.playerData.lastPlayedAt}
            display="relative"
            fallback="N/A"
          />
        </div>
      ),
    },
  ]
}
