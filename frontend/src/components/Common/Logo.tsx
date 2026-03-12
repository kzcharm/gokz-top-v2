import { Link } from "@tanstack/react-router"

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
  const logoMark = (
    <img
      src="/apple-touch-icon.png"
      alt="GOKZ TOP"
      className={cn("size-8 rounded-xl shadow-sm", className)}
    />
  )

  const fullLogo = (
    <span className="flex items-center gap-3">
      {logoMark}
      <span className="text-foreground text-sm font-semibold tracking-wide whitespace-nowrap">
        GOKZ TOP
      </span>
    </span>
  )

  const content =
    variant === "responsive" ? (
      <>
        <span className="group-data-[collapsible=icon]:hidden">{fullLogo}</span>
        <img
          src="/apple-touch-icon.png"
          alt="GOKZ TOP"
          className={cn(
            "size-8 rounded-xl shadow-sm hidden group-data-[collapsible=icon]:block",
            className,
          )}
        />
      </>
    ) : (
      (variant === "full" ? fullLogo : logoMark)
    )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}
