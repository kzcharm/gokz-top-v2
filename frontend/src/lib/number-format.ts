import { getLocale } from "@/i18n/locale"

export function formatFlooredDecimal(
  value: number,
  fractionDigits: number,
  locale: string = getLocale(),
) {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    roundingMode: "floor",
  } as Intl.NumberFormatOptions).format(value)
}
