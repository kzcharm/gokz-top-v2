export const SITE_NAME = "GOKZ.TOP"
export const SITE_START_YEAR = 2024

export function getPageTitle(pageTitle?: string): string {
  return pageTitle ? `${pageTitle} | ${SITE_NAME}` : SITE_NAME
}

export function getCopyrightYearRange(year = new Date().getFullYear()): string {
  return year <= SITE_START_YEAR
    ? `${SITE_START_YEAR}`
    : `${SITE_START_YEAR} - ${year}`
}
