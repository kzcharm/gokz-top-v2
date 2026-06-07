import { Link } from "@tanstack/react-router"

import type { ServerGroupSummary } from "@/client"
import { cn, truncateText } from "@/lib/utils"

interface RecordServerDisplayProps {
  serverName: string
  serverGroup?: ServerGroupSummary | null
  className?: string
  maxLength?: number
}

export function RecordServerDisplay({
  serverName,
  serverGroup,
  className,
  maxLength = 32,
}: RecordServerDisplayProps) {
  const label = serverGroup?.name?.trim() || serverName
  const title = label || serverName
  const content = truncateText(label, maxLength)

  if (serverGroup) {
    return (
      <Link
        to="/servers/group/$customId"
        params={{ customId: serverGroup.custom_id }}
        className={cn(
          "block max-w-[14rem] truncate text-sm text-foreground/90 underline-offset-4 hover:text-primary hover:underline",
          className,
        )}
        title={title}
      >
        {content}
      </Link>
    )
  }

  return (
    <span
      className={cn(
        "block max-w-[14rem] truncate text-sm text-foreground/90",
        className,
      )}
      title={title}
    >
      {content}
    </span>
  )
}
