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
  value: string | Date | null | undefined
}

export function FormattedDateTime({
  className,
  value,
  ...options
}: FormattedDateTimeProps) {
  const { formatDateTime } = useDateTimeFormat()
  const formattedValue = formatDateTime(value, options)
  const isRelativeDisplay =
    options.display === "relative" || options.display === "contextual-relative"
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
