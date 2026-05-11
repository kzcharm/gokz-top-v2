import { useEffect, useState } from "react"
import { useDateTimeFormat } from "@/components/date-time-format-provider"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { DateTimeFormatOptions } from "@/lib/date-time"
import { cn } from "@/lib/utils"

interface FormattedDateTimeProps extends DateTimeFormatOptions {
  className?: string
  tickerMs?: number
  value: string | Date | null | undefined
}

export function FormattedDateTime({
  className,
  tickerMs = 1000,
  value,
  ...options
}: FormattedDateTimeProps) {
  const { formatDateTime } = useDateTimeFormat()
  const isRelativeDisplay =
    options.display === "relative" || options.display === "contextual-relative"
  const [, setTick] = useState(0)

  useEffect(() => {
    if (!isRelativeDisplay || tickerMs <= 0 || !value) {
      return
    }

    const intervalId = window.setInterval(() => {
      setTick((currentTick) => currentTick + 1)
    }, tickerMs)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [isRelativeDisplay, tickerMs, value])

  const formattedValue = formatDateTime(value, options)
  const hoverValue = formatDateTime(value, {
    ...options,
    display: isRelativeDisplay ? "absolute" : "relative",
  })
  const tooltipContent =
    formattedValue !== hoverValue &&
    hoverValue !== (options.fallback ?? "Unknown")
      ? hoverValue
      : undefined

  const content = <span className={cn(className)}>{formattedValue}</span>

  if (!tooltipContent) {
    return content
  }

  return (
    <Tooltip delayDuration={500}>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent
        hideArrow
        sideOffset={4}
        className="rounded-sm border border-border bg-background px-2 py-1 font-normal text-foreground shadow-md"
      >
        {tooltipContent}
      </TooltipContent>
    </Tooltip>
  )
}
