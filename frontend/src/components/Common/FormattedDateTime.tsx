import { useDateTimeFormat } from "@/components/date-time-format-provider"
import { cn } from "@/lib/utils"
import type { DateTimeFormatOptions } from "@/lib/date-time"

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

  return <span className={cn(className)}>{formatDateTime(value, options)}</span>
}
