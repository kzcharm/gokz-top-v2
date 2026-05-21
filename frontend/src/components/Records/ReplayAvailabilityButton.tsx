import { Play } from "lucide-react"
import { useTranslation } from "react-i18next"

import type { RecordPublic } from "@/client"
import { Button } from "@/components/ui/button"
import { buildRunReplayViewerUrl, openReplayViewer } from "@/lib/replay-viewer"
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
  const { t } = useTranslation()

  if (!hasReplayAvailable(record)) {
    return null
  }

  const playLabel = t("common.playRunReplay")

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label={playLabel}
      title={playLabel}
      onClick={() => openReplayViewer(buildRunReplayViewerUrl(record.uuid))}
      className={cn(
        "size-8 rounded-full text-foreground/70 opacity-100",
        className,
      )}
    >
      <Play className="size-3.5" />
    </Button>
  )
}
