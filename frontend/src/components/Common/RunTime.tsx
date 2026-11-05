import { useCallback } from "react"
import { useGlobalPreferences } from "@/components/global-preferences-provider"
import { formatRunTime, RUN_TIME_FONT_FAMILIES } from "@/lib/run-time"
import { cn } from "@/lib/utils"

export function useRunTimeFontFamily() {
  const { runTimeFont } = useGlobalPreferences()
  return RUN_TIME_FONT_FAMILIES[runTimeFont]
}

export function useRunTimeFormat() {
  const { showMilliseconds } = useGlobalPreferences()
  return useCallback(
    (seconds: number) => formatRunTime(seconds, showMilliseconds),
    [showMilliseconds],
  )
}

export function RunTime({
  seconds,
  className,
}: {
  seconds: number
  className?: string
}) {
  const format = useRunTimeFormat()
  return <span className={cn("run-time", className)}>{format(seconds)}</span>
}
