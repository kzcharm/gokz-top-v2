import type { ReactNode } from "react"

import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export function AdminPageHeader({
  title,
  aside,
}: {
  title: ReactNode
  aside?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      {aside ? <div className="flex items-center gap-3">{aside}</div> : null}
    </div>
  )
}

export function AdminControlsCard({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <Card
      className={cn(
        "gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0",
        className,
      )}
    >
      <CardContent className="p-6 sm:px-8 sm:py-6">{children}</CardContent>
    </Card>
  )
}

export function AdminTableCard({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <Card
      className={cn(
        "gap-0 overflow-visible rounded-[28px] border-border/70 bg-card/95 py-0",
        className,
      )}
    >
      <CardContent className="p-0 [&_[data-slot=table-container]]:rounded-none [&_[data-slot=table-container]]:border-0">
        {children}
      </CardContent>
    </Card>
  )
}
