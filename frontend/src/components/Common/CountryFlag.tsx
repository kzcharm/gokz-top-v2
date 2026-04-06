import * as Flags from "country-flag-icons/react/3x2"
import type { ComponentType, SVGProps } from "react"

import noneFlagSrc from "@/assets/flags/none.svg"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

const countryNameFormatter =
  typeof Intl !== "undefined" && "DisplayNames" in Intl
    ? new Intl.DisplayNames(["en"], { type: "region" })
    : null

const flagComponents = Flags as Record<
  string,
  ComponentType<SVGProps<SVGSVGElement>>
>

interface CountryFlagProps {
  countryCode?: string | null
  className?: string
  fallbackClassName?: string
  showTooltip?: boolean
}

export function getCountryName(countryCode?: string | null) {
  if (!countryCode) {
    return null
  }

  const normalizedCountryCode = countryCode.toUpperCase()
  if (!countryNameFormatter) {
    return normalizedCountryCode
  }

  return countryNameFormatter.of(normalizedCountryCode) || normalizedCountryCode
}

export function CountryFlag({
  countryCode,
  className,
  fallbackClassName,
  showTooltip = true,
}: CountryFlagProps) {
  const normalizedCountryCode = countryCode?.toUpperCase() || null
  const FlagComponent = normalizedCountryCode
    ? flagComponents[normalizedCountryCode]
    : null
  const countryName = getCountryName(normalizedCountryCode)

  if (!FlagComponent) {
    return (
      <img
        src={noneFlagSrc}
        alt="Unknown country"
        className={cn(
          "h-4 w-6 shrink-0 rounded-[2px] border border-border/80",
          fallbackClassName,
        )}
        title="Unknown country"
      />
    )
  }

  const content = (
    <FlagComponent
      role="img"
      aria-label={countryName || normalizedCountryCode || "Unknown country"}
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
