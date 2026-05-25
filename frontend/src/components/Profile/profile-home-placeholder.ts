import { getTierColor } from "@/components/Servers/tier"

export type ProfileActivityYear = "2025" | "2026"

export type ProfileHomePlaceholder = {
  summary: {
    points: number
    globalRank: number
    rating: number
    ratingTier: string
    regionalRank: number
    regionalLabel: string
    playtimeHours: number
    profileViews: number
    likes: number
  }
  skills: Array<{
    label: string
    shortLabel: string
    value: number
    tone: string
  }>
  completion: {
    overall: {
      completed: number
      total: number
      tiers: Array<{
        label: string
        complete: number
        total: number
        color: string
      }>
    }
    pro: {
      completed: number
      total: number
      tiers: Array<{
        label: string
        complete: number
        total: number
        color: string
      }>
    }
  }
  activity: Record<ProfileActivityYear, number[]>
  pinnedRecords: Array<{
    map: string
    mode: string
    variant: string
    rank: string
    time: string
    badge: string
    badgeTone: string
    achievedOn: string
  }>
}

function buildActivity(seed: number) {
  return Array.from({ length: 53 * 7 }, (_, index) => {
    const week = Math.floor(index / 7)
    const day = index % 7
    const raw = (week * 7 + day * 3 + seed) % 17

    if (raw < 5) {
      return 0
    }
    if (raw < 9) {
      return 1
    }
    if (raw < 12) {
      return 2
    }
    if (raw < 15) {
      return 3
    }
    return 4
  })
}

export const profileHomePlaceholder: ProfileHomePlaceholder = {
  summary: {
    points: 14802,
    globalRank: 118,
    rating: 9341,
    ratingTier: "Legend",
    regionalRank: 31,
    regionalLabel: "EU Regional",
    playtimeHours: 4812,
    profileViews: 12480,
    likes: 106,
  },
  skills: [
    { label: "Boxtech", shortLabel: "BX", value: 84, tone: "violet" },
    { label: "Strafe", shortLabel: "ST", value: 79, tone: "sky" },
    { label: "Bhop", shortLabel: "BH", value: 88, tone: "emerald" },
    { label: "Climb", shortLabel: "CL", value: 73, tone: "amber" },
    { label: "Ladder", shortLabel: "LD", value: 67, tone: "orange" },
    { label: "Slide", shortLabel: "SL", value: 82, tone: "stone" },
  ],
  completion: {
    overall: {
      completed: 487,
      total: 780,
      tiers: Array.from({ length: 8 }, (_, index) => {
        const values = [
          [120, 120],
          [98, 105],
          [90, 110],
          [72, 108],
          [55, 102],
          [32, 90],
          [15, 85],
          [5, 60],
        ][index]
        return {
          label: `T${index + 1}`,
          complete: values[0],
          total: values[1],
          color: getTierColor(index + 1) ?? "#6B7280",
        }
      }),
    },
    pro: {
      completed: 231,
      total: 780,
      tiers: Array.from({ length: 8 }, (_, index) => {
        const values = [
          [80, 120],
          [55, 105],
          [40, 110],
          [28, 108],
          [15, 102],
          [7, 90],
          [4, 85],
          [2, 60],
        ][index]
        return {
          label: `T${index + 1}`,
          complete: values[0],
          total: values[1],
          color: getTierColor(index + 1) ?? "#6B7280",
        }
      }),
    },
  },
  activity: {
    "2025": buildActivity(3),
    "2026": buildActivity(9),
  },
  pinnedRecords: [
    {
      map: "kz_longjumps",
      mode: "KZT",
      variant: "PRO",
      rank: "#1 Global",
      time: "1:14.320",
      badge: "WR",
      badgeTone: "emerald",
      achievedOn: "Mar 2026",
    },
    {
      map: "kz_bhop_monster",
      mode: "KZT",
      variant: "PRO",
      rank: "#3 Global",
      time: "2:31.083",
      badge: "Top 10",
      badgeTone: "violet",
      achievedOn: "Jan 2026",
    },
    {
      map: "kz_volcano",
      mode: "KZT",
      variant: "TP",
      rank: "#1 Global",
      time: "4:02.441",
      badge: "WR",
      badgeTone: "emerald",
      achievedOn: "Feb 2026",
    },
    {
      map: "kz_checkmate",
      mode: "SKZ",
      variant: "PRO",
      rank: "#7 Global",
      time: "3:18.762",
      badge: "Top 10",
      badgeTone: "sky",
      achievedOn: "Dec 2025",
    },
    {
      map: "kz_deathrun_adv",
      mode: "VNL",
      variant: "PRO",
      rank: "#2 Global",
      time: "5:44.190",
      badge: "Top 5",
      badgeTone: "amber",
      achievedOn: "Nov 2025",
    },
    {
      map: "kz_bhop_arcane",
      mode: "KZT",
      variant: "PRO",
      rank: "#1 Global",
      time: "0:58.032",
      badge: "WR",
      badgeTone: "emerald",
      achievedOn: "Mar 2026",
    },
  ],
}
