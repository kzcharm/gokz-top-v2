import level0 from "@/assets/faceit-levels/0.svg"
import level1 from "@/assets/faceit-levels/1.svg"
import level2 from "@/assets/faceit-levels/2.svg"
import level3 from "@/assets/faceit-levels/3.svg"
import level4 from "@/assets/faceit-levels/4.svg"
import level5 from "@/assets/faceit-levels/5.svg"
import level6 from "@/assets/faceit-levels/6.svg"
import level7 from "@/assets/faceit-levels/7.svg"
import level8 from "@/assets/faceit-levels/8.svg"
import level9 from "@/assets/faceit-levels/9.svg"
import level10 from "@/assets/faceit-levels/10.svg"
import level11 from "@/assets/faceit-levels/11.svg"

const FACEIT_LEVEL_THRESHOLDS = [
  2.01, 3.67, 4.55, 5.2, 6.04, 6.84, 7.74, 8.64, 9.54, 10.5,
] as const

const FACEIT_LEVEL_ICON_BY_LEVEL = {
  0: level0,
  1: level1,
  2: level2,
  3: level3,
  4: level4,
  5: level5,
  6: level6,
  7: level7,
  8: level8,
  9: level9,
  10: level10,
  11: level11,
} as const

export type PlayerRatingLevel = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11

export function getPlayerRatingLevel(
  rating: number | null | undefined,
): PlayerRatingLevel {
  if (rating === null || rating === undefined || rating <= 0) {
    return 0
  }

  for (let index = FACEIT_LEVEL_THRESHOLDS.length - 1; index >= 0; index -= 1) {
    if (rating >= FACEIT_LEVEL_THRESHOLDS[index]) {
      return (index + 2) as PlayerRatingLevel
    }
  }

  return 1
}

export function getPlayerRatingBadgeIcon(level: PlayerRatingLevel): string {
  return FACEIT_LEVEL_ICON_BY_LEVEL[level]
}
