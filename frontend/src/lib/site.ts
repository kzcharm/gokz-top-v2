export const SITE_NAME = "GOKZ.TOP"
export const SITE_START_YEAR = 2024

function getAppVersionLabel(version: string): string {
  if (import.meta.env.DEV) {
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
