import { Link } from "@tanstack/react-router"

import { SITE_NAME } from "@/lib/site"
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
  const logoSrc =
    variant === "responsive" ? "/logo-mark-square.png" : "/apple-touch-icon.png"
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

  const fullLogo = (
    <span className="flex items-center gap-3">
      {logoMark}
      <span className="text-primary text-xl font-bold tracking-wide whitespace-nowrap">
        {SITE_NAME}
      </span>
    </span>
  )

  const content =
    variant === "responsive" ? (
      <>
        <span className="group-data-[collapsible=icon]:hidden">{fullLogo}</span>
        <img
          src="/logo-mark-square.png"
          alt={SITE_NAME}
          className={cn(
            "size-8 rounded-lg shadow-[0_1px_2px_rgb(0_0_0_/_0.08)] hidden group-data-[collapsible=icon]:block",
            className,
          )}
        />
      </>
    ) : variant === "full" ? (
      fullLogo
    ) : (
      logoMark
    )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}
