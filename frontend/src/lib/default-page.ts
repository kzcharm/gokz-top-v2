export const DEFAULT_PAGE_STORAGE_KEY = "gokz-default-page"

export const DEFAULT_PAGE_OPTIONS = [
  "/servers",
  "/profile",
  "/leaderboards",
  "/maps",
  "/live",
] as const

export type DefaultPagePreference = (typeof DEFAULT_PAGE_OPTIONS)[number]

export const FALLBACK_DEFAULT_PAGE: DefaultPagePreference = "/servers"

export function isDefaultPagePreference(
  value: string | null,
): value is DefaultPagePreference {
  return DEFAULT_PAGE_OPTIONS.includes(value as DefaultPagePreference)
}

export function readDefaultPagePreference(): DefaultPagePreference {
  try {
    const value = localStorage.getItem(DEFAULT_PAGE_STORAGE_KEY)
    return isDefaultPagePreference(value) ? value : FALLBACK_DEFAULT_PAGE
  } catch {
    return FALLBACK_DEFAULT_PAGE
  }
}

export function writeDefaultPagePreference(value: DefaultPagePreference) {
  localStorage.setItem(DEFAULT_PAGE_STORAGE_KEY, value)
}

export function getDefaultPageHref(
  preference: DefaultPagePreference,
  steamid64: string | null,
) {
  if (preference === "/profile") {
    return steamid64 ? `/profile/${steamid64}` : FALLBACK_DEFAULT_PAGE
  }

  return preference
}
