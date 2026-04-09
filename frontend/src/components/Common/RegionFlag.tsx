import type { ReactElement } from "react"

import noneFlagSrc from "@/assets/flags/none.svg"
import auFlagSrc from "@/assets/flags/regions/au.svg"
import cnFlagSrc from "@/assets/flags/regions/cn.svg"
import euFlagSrc from "@/assets/flags/regions/eu.svg"
import usFlagSrc from "@/assets/flags/regions/us.svg"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

const REGION_NAMES: Record<string, string> = {
  AF: "Africa",
  AS: "Asia",
  CIS: "CIS",
  CN: "China",
  EU: "Europe",
  ME: "Middle East",
  NA: "North America",
  OC: "Oceania",
  SA: "South America",
}

const REGION_FLAG_IMAGE_SOURCES: Record<string, string> = {
  CIS: "https://upload.wikimedia.org/wikipedia/commons/1/11/Flag_of_the_CIS.svg",
  CN: cnFlagSrc,
  EU: euFlagSrc,
  NA: usFlagSrc,
  OC: auFlagSrc,
  SA: "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d9/Flag_of_UNASUR.svg/1920px-Flag_of_UNASUR.svg.png",
}

const REGION_FLAG_IMAGE_CLASS_NAMES: Record<string, string> = {
  CIS: "object-cover",
}

interface RegionFlagProps {
  regionCode?: string | null
  regionName?: string | null
  className?: string
  fallbackClassName?: string
  showTooltip?: boolean
  decorative?: boolean
}

interface RegionBadgeProps {
  regionCode?: string | null
  regionName?: string | null
  className?: string
}

export function getRegionName(regionCode?: string | null) {
  if (!regionCode) {
    return null
  }

  return REGION_NAMES[regionCode.toUpperCase()] ?? regionCode.toUpperCase()
}

function RegionFlagImage({
  src,
  label,
  className,
  decorative,
}: {
  src: string
  label: string
  className?: string
  decorative?: boolean
}) {
  return (
    <img
      src={src}
      alt={decorative ? "" : label}
      aria-hidden={decorative || undefined}
      className={cn("h-full w-full object-fill", className)}
      title={decorative ? undefined : label}
    />
  )
}

function RegionFlagFrame({
  children,
  className,
}: {
  children: ReactElement
  className?: string
}) {
  return (
    <span
      className={cn(
        "h-4 w-[21px] shrink-0 overflow-hidden rounded-[2px] border border-border/80",
        className,
      )}
    >
      {children}
    </span>
  )
}

export function RegionFlag({
  regionCode,
  regionName,
  className,
  fallbackClassName,
  showTooltip = true,
  decorative = false,
}: RegionFlagProps) {
  const normalizedRegionCode = regionCode?.toUpperCase() || null
  const label =
    regionName || getRegionName(normalizedRegionCode) || "Unknown region"

  if (!normalizedRegionCode) {
    return (
      <RegionFlagFrame className={fallbackClassName}>
        <RegionFlagImage
          src={noneFlagSrc}
          label="Unknown region"
          decorative={decorative}
        />
      </RegionFlagFrame>
    )
  }

  const imageSrc = REGION_FLAG_IMAGE_SOURCES[normalizedRegionCode]
  const imageClassName = normalizedRegionCode
    ? REGION_FLAG_IMAGE_CLASS_NAMES[normalizedRegionCode]
    : undefined

  let content: ReactElement
  if (imageSrc) {
    content = (
      <RegionFlagFrame className={className}>
        <RegionFlagImage
          src={imageSrc}
          label={label}
          className={imageClassName}
          decorative={decorative}
        />
      </RegionFlagFrame>
    )
  } else {
    content = (
      <RegionFlagFrame className={fallbackClassName}>
        <RegionFlagImage
          src={noneFlagSrc}
          label={label}
          decorative={decorative}
        />
      </RegionFlagFrame>
    )
  }

  if (!showTooltip || decorative) {
    return content
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent sideOffset={8}>{label}</TooltipContent>
    </Tooltip>
  )
}

export function RegionBadge({
  regionCode,
  regionName,
  className,
}: RegionBadgeProps) {
  const normalizedRegionCode = regionCode?.toUpperCase() || null

  if (!normalizedRegionCode) {
    return null
  }

  return (
    <span className={cn("flex min-w-0 items-center gap-2", className)}>
      <RegionFlag
        regionCode={normalizedRegionCode}
        regionName={regionName}
        showTooltip={false}
        decorative
      />
      <span className="truncate">{normalizedRegionCode}</span>
    </span>
  )
}
