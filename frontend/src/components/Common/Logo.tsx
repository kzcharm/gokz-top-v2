import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import {
  APP_VERSION_LABEL,
  BRAND_MARK_SRC,
  COMPACT_BRAND_MARK_SRC,
  SITE_NAME,
} from "@/lib/site"
import { cn } from "@/lib/utils"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const { t } = useTranslation()
  const logoSrc =
    variant === "responsive" ? COMPACT_BRAND_MARK_SRC : BRAND_MARK_SRC
  const markClassName =
    variant === "responsive"
      ? "size-8 rounded-lg shadow-[0_1px_2px_rgb(0_0_0_/_0.08)]"
      : "size-8 rounded-xl shadow-sm"

  const logoMark = (
    <img
      src={logoSrc}
      alt={SITE_NAME}
      className={cn(markClassName, className)}
    />
  )

  const logoMarkContent = asLink ? <Link to="/">{logoMark}</Link> : logoMark

  const siteNameContent = (
    <span className="text-primary text-xl font-bold tracking-wide">
      {SITE_NAME}
    </span>
  )

  const linkedSiteNameContent = asLink ? (
    <Link
      to="/"
      className="rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      {siteNameContent}
    </Link>
  ) : (
    siteNameContent
  )

  const versionLabel = (
    <Link
      to="/updates"
      aria-label={t("updates.openReleaseNotes")}
      className="rounded-sm text-muted-foreground text-xs font-semibold tracking-normal transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      {APP_VERSION_LABEL}
    </Link>
  )

  const fullLogo = (
    <span className="flex items-center gap-3">
      {logoMarkContent}
      <span className="flex items-baseline gap-2 whitespace-nowrap">
        {linkedSiteNameContent}
        {versionLabel}
      </span>
    </span>
  )

  const content =
    variant === "responsive" ? (
      <>
        <span className="group-data-[collapsible=icon]:hidden">{fullLogo}</span>
        {asLink ? (
          <Link to="/">
            <img
              src={COMPACT_BRAND_MARK_SRC}
              alt={SITE_NAME}
              className={cn(
                "size-8 rounded-lg shadow-[0_1px_2px_rgb(0_0_0_/_0.08)] hidden group-data-[collapsible=icon]:block",
                className,
              )}
            />
          </Link>
        ) : (
          <img
            src={COMPACT_BRAND_MARK_SRC}
            alt={SITE_NAME}
            className={cn(
              "size-8 rounded-lg shadow-[0_1px_2px_rgb(0_0_0_/_0.08)] hidden group-data-[collapsible=icon]:block",
              className,
            )}
          />
        )}
      </>
    ) : variant === "full" ? (
      fullLogo
    ) : (
      logoMark
    )

  if (!asLink || variant !== "icon") {
    return content
  }

  return <Link to="/">{content}</Link>
}
