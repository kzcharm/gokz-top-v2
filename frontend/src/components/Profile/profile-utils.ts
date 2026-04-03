import { type PlayerPublic, PlayersService } from "@/client"

export type ProfileTab = "home" | "records" | "stats"

export const profileBadgeToneClasses: Record<string, string> = {
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

export async function fetchProfilePlayer(identifier: string) {
  return await PlayersService.readPlayer({
    identifier,
  })
}

export function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value)
}

export function formatHours(hours: number) {
  return `${formatNumber(hours)} hrs`
}

export function formatCompactPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

export function formatRatingBadge(value: number) {
  return (value / 1158).toFixed(2)
}

export function getAvatarUrl(player: PlayerPublic) {
  if (!player.avatar_hash) {
    return null
  }

  return `https://avatars.steamstatic.com/${player.avatar_hash}_full.jpg`
}
