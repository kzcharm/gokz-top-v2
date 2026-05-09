import * as Flags from "country-flag-icons/react/3x2"
import type { ComponentType, SVGProps } from "react"
import { useTranslation } from "react-i18next"

import noneFlagSrc from "@/assets/flags/none.svg"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { compareLocaleText, getLocale } from "@/i18n/locale"
import { cn } from "@/lib/utils"

const flagComponents = Flags as Record<
  string,
  ComponentType<SVGProps<SVGSVGElement>>
>

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
  return Object.keys(flagComponents)
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
  const FlagComponent = normalizedCountryCode
    ? flagComponents[normalizedCountryCode]
    : null
  const countryName = getCountryName(
    normalizedCountryCode,
    i18n.resolvedLanguage,
  )

  if (!FlagComponent) {
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
    <FlagComponent
      role="img"
      aria-label={
        countryName || normalizedCountryCode || t("common.unknownCountry")
      }
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
