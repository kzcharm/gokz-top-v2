export const randomTeamName = () =>
  `Team ${Math.random().toString(36).substring(7)}`

export const randomPassword = () => `${Math.random().toString(36).substring(2)}`

export const randomSteamid64 = () => {
  const suffix = Math.floor(Math.random() * 9_000_000) + 1_000_000
  return (BigInt("76561198000000000") + BigInt(suffix)).toString()
}

export const slugify = (text: string) =>
  text
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^\w-]+/g, "")
