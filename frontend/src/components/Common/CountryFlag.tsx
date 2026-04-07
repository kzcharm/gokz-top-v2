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

function resolveCountryName(countryCode: string | null) {
  if (!countryCode) {
    return null
  }

  if (!countryNameFormatter) {
    return countryCode
  }

  try {
    return countryNameFormatter.of(countryCode) || countryCode
  } catch {
    return countryCode
  }
}

export const countryOptions = Object.keys(flagComponents)
  .map((countryCode) => ({
    countryCode,
    name: resolveCountryName(countryCode) || countryCode,
  }))
  .sort((left, right) => left.name.localeCompare(right.name))

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
  return resolveCountryName(normalizedCountryCode) || normalizedCountryCode
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
