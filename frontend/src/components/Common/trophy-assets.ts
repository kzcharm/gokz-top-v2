export const TROPHY_ASSETS = {
  gold: "https://kzgo.eu/trophy4.png",
  silver: "https://kzgo.eu/trophy_silver2.png",
  bronze: "https://kzgo.eu/trophy_bronze.png",
} as const

export type TrophyAsset = keyof typeof TROPHY_ASSETS
