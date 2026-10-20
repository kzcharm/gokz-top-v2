import { cn } from "@/lib/utils"

interface NotificationDotProps {
  className?: string
  pulse?: boolean
}

export function NotificationDot({
  className,
  pulse = false,
}: NotificationDotProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "size-2 shrink-0 rounded-full bg-red-500",
        pulse && "animate-pulse",
        className,
      )}
    />
  )
}
