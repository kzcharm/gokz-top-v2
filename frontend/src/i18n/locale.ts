import i18n, { getCurrentLocale, normalizeLocale } from "@/i18n"

export function getLocale() {
  return getCurrentLocale()
}

export function getNumberFormatter(
  options?: Intl.NumberFormatOptions,
  locale: string = getLocale(),
) {
  return new Intl.NumberFormat(locale, options)
}

export function formatNumber(
  value: number,
  options?: Intl.NumberFormatOptions,
  locale: string = getLocale(),
) {
  return getNumberFormatter(options, locale).format(value)
}

export function compareLocaleText(
  left: string,
  right: string,
  options?: Intl.CollatorOptions,
  locale: string = getLocale(),
) {
  return new Intl.Collator(locale, options).compare(left, right)
}

export function asSupportedLocale(locale: string | null | undefined) {
  return normalizeLocale(locale)
}

export function translate(key: string, options?: Record<string, unknown>) {
  return i18n.t(key, options)
}
