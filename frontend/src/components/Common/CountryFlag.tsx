import { useTranslation } from "react-i18next"

import noneFlagSrc from "@/assets/flags/none.svg"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { compareLocaleText, getLocale } from "@/i18n/locale"
import { cn } from "@/lib/utils"

const flagUrls = import.meta.glob<string>("@flags/*.svg", {
  eager: true,
  import: "default",
  query: "?url&no-inline",
})
const flagSources = Object.fromEntries(
  Object.entries(flagUrls).map(([path, url]) => [
    path.slice(path.lastIndexOf("/") + 1, -4).replace(/-/g, "_"),
    url,
  ]),
)

export function getCountryFlagSrc(countryCode?: string | null) {
  return countryCode ? flagSources[countryCode.toUpperCase()] : undefined
}

function resolveCountryName(
  countryCode: string | null,
  locale: string = getLocale(),
) {
  if (!countryCode) {
    return null
  }

  if (typeof Intl === "undefined" || !("DisplayNames" in Intl)) {
    return countryCode
  }

  try {
    return (
      new Intl.DisplayNames([locale], { type: "region" }).of(countryCode) ||
      countryCode
    )
  } catch {
    return countryCode
  }
}

export function getCountryOptions(locale: string = getLocale()) {
  return Object.keys(flagSources)
    .map((countryCode) => ({
      countryCode,
      name: resolveCountryName(countryCode, locale) || countryCode,
    }))
    .sort((left, right) => compareLocaleText(left.name, right.name, {}, locale))
}

interface CountryFlagProps {
  countryCode?: string | null
  className?: string
  fallbackClassName?: string
  showTooltip?: boolean
}

export function getCountryName(
  countryCode?: string | null,
  locale: string = getLocale(),
) {
  if (!countryCode) {
    return null
  }

  const normalizedCountryCode = countryCode.toUpperCase()
  return (
    resolveCountryName(normalizedCountryCode, locale) || normalizedCountryCode
  )
}

export function CountryFlag({
  countryCode,
  className,
  fallbackClassName,
  showTooltip = true,
}: CountryFlagProps) {
  const { t, i18n } = useTranslation()
  const normalizedCountryCode = countryCode?.toUpperCase() || null
  const flagSrc = getCountryFlagSrc(normalizedCountryCode)
  const countryName = getCountryName(
    normalizedCountryCode,
    i18n.resolvedLanguage,
  )

  if (!flagSrc) {
    return (
      <img
        src={noneFlagSrc}
        alt={t("common.unknownCountry")}
        className={cn(
          "h-4 w-6 shrink-0 rounded-[2px] border border-border/80",
          fallbackClassName,
        )}
        title={t("common.unknownCountry")}
      />
    )
  }

  const content = (
    <img
      src={flagSrc}
      loading="lazy"
      alt={countryName || normalizedCountryCode || t("common.unknownCountry")}
      className={cn("h-4 w-6 shrink-0", className)}
    />
  )

  if (!showTooltip) {
    return content
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent sideOffset={8}>
        {countryName || normalizedCountryCode}
      </TooltipContent>
    </Tooltip>
  )
}
