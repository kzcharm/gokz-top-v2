import { Play } from "lucide-react"

import type { RecordPublic } from "@/client"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type ReplayAvailabilityRecord = RecordPublic & {
  is_replay_available?: boolean
}

export function hasReplayAvailable(record: RecordPublic) {
  return (record as ReplayAvailabilityRecord).is_replay_available === true
}

export function ReplayAvailabilityButton({
  record,
  className,
}: {
  record: RecordPublic
  className?: string
}) {
  if (!hasReplayAvailable(record)) {
    return null
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      disabled
      aria-label="Replay available"
      title="Replay available"
      className={cn(
        "size-8 rounded-full text-foreground/70 opacity-100 disabled:pointer-events-none disabled:opacity-100",
        className,
      )}
    >
      <Play className="size-3.5" />
    </Button>
  )
}
