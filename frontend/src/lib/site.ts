export const SITE_NAME = "GOKZ.TOP"
export const SITE_DEFAULT_TITLE =
  "GOKZ.TOP - GOKZ Records, Leaderboards, Maps and Servers"
export const SITE_DEFAULT_DESCRIPTION =
  "Track GOKZ player profiles, records, leaderboards, maps, live servers, jumpstats, and replays."
export const SITE_START_YEAR = 2024
export const IS_LOCAL_DEV = import.meta.env.DEV
export const BRAND_MARK_SRC = IS_LOCAL_DEV
  ? "/apple-touch-icon-dev.png"
  : "/apple-touch-icon.png"
export const COMPACT_BRAND_MARK_SRC = IS_LOCAL_DEV
  ? "/logo-mark-square-dev.png"
  : "/logo-mark-square.png"

function getAppVersionLabel(version: string): string {
  if (IS_LOCAL_DEV) {
    return "dev"
  }

  const semverMatch = version.match(/^(v\d+\.\d+\.\d+)/)

  if (semverMatch) {
    return semverMatch[1]
  }

  if (/^[0-9a-f]{7,40}$/i.test(version)) {
    return "dev"
  }

  return version
}

export const APP_VERSION_LABEL = getAppVersionLabel(__APP_VERSION__)

export function getPageTitle(pageTitle?: string): string {
  return pageTitle ? `${SITE_NAME} - ${pageTitle}` : SITE_NAME
}

export function getCopyrightYearRange(year = new Date().getFullYear()): string {
  return year <= SITE_START_YEAR
    ? `${SITE_START_YEAR}`
    : `${SITE_START_YEAR} - ${year}`
}
