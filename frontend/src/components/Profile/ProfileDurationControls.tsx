import { ChevronLeft, ChevronRight } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

type DurationSpecialView = {
  id: string
  label: string
  testId: string
}

type ProfileDurationControlsProps = {
  activeViewId: string
  defaultYearId?: string | null
  onActiveViewIdChange: (viewId: string) => void
  onPlayingChange: (isPlaying: boolean) => void
  specialViews: DurationSpecialView[]
  testIdPrefix: string
  yearIds: string[]
}

export function ProfileDurationControls({
  activeViewId,
  defaultYearId,
  onActiveViewIdChange,
  onPlayingChange,
  specialViews,
  testIdPrefix,
  yearIds,
}: ProfileDurationControlsProps) {
  const { t } = useTranslation()
  const fallbackYearId = useMemo(() => {
    if (defaultYearId && yearIds.includes(defaultYearId)) {
      return defaultYearId
    }

    return yearIds[yearIds.length - 1] ?? ""
  }, [defaultYearId, yearIds])
  const lastYearIdRef = useRef(fallbackYearId)
  const [yearInputValue, setYearInputValue] = useState(fallbackYearId)
  const selectedYearId = yearIds.includes(lastYearIdRef.current)
    ? lastYearIdRef.current
    : fallbackYearId
  const selectedYearIndex = yearIds.indexOf(selectedYearId)
  const hasYears = yearIds.length > 0
  const canStepPrevious = selectedYearIndex > 0
  const canStepNext =
    selectedYearIndex >= 0 && selectedYearIndex < yearIds.length - 1

  useEffect(() => {
    if (!hasYears) {
      lastYearIdRef.current = ""
      setYearInputValue("")
      onPlayingChange(false)
      return
    }

    if (!yearIds.includes(lastYearIdRef.current)) {
      lastYearIdRef.current = fallbackYearId
      setYearInputValue(fallbackYearId)
    }
  }, [fallbackYearId, hasYears, onPlayingChange, yearIds])

  useEffect(() => {
    if (yearIds.includes(activeViewId)) {
      lastYearIdRef.current = activeViewId
      setYearInputValue(activeViewId)
    }
  }, [activeViewId, yearIds])

  const activateYear = (yearId: string) => {
    if (!yearIds.includes(yearId)) {
      return
    }

    lastYearIdRef.current = yearId
    setYearInputValue(yearId)
    onActiveViewIdChange(yearId)
    onPlayingChange(false)
  }

  const activateYearByIndex = (index: number) => {
    const yearId = yearIds[index]
    if (yearId) {
      activateYear(yearId)
    }
  }

  const commitYearInputValue = () => {
    if (!hasYears) {
      setYearInputValue("")
      return
    }

    const nextYear = Number(yearInputValue)
    if (!Number.isFinite(nextYear)) {
      setYearInputValue(selectedYearId)
      return
    }

    const nextYearId = String(Math.trunc(nextYear))
    if (yearIds.includes(nextYearId)) {
      activateYear(nextYearId)
      return
    }

    const clampedYear = Math.min(
      Math.max(Math.trunc(nextYear), Number(yearIds[0])),
      Number(yearIds[yearIds.length - 1]),
    )
    const closestYearId =
      yearIds.find((yearId) => Number(yearId) >= clampedYear) ??
      yearIds[yearIds.length - 1]

    if (closestYearId) {
      activateYear(closestYearId)
    } else {
      setYearInputValue(selectedYearId)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-x-1">
        <Button
          variant="outline"
          size="sm"
          className="h-8 w-10 p-0"
          onClick={() => activateYearByIndex(selectedYearIndex - 1)}
          disabled={!hasYears || !canStepPrevious}
          data-testid={`${testIdPrefix}-previous-year`}
        >
          <span className="sr-only">{t("profile.duration.previousYear")}</span>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Input
          type="number"
          inputMode="numeric"
          min={yearIds[0]}
          max={yearIds[yearIds.length - 1]}
          value={yearInputValue}
          onChange={(event) => {
            setYearInputValue(event.target.value)
          }}
          onBlur={commitYearInputValue}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault()
              commitYearInputValue()
            }
          }}
          disabled={!hasYears}
          className="h-8 w-16 rounded-md border-border bg-muted px-2 text-center text-sm font-medium text-foreground [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
          aria-label={t("profile.duration.yearInput")}
          data-testid={`${testIdPrefix}-year-input`}
        />
        <Button
          variant="outline"
          size="sm"
          className="h-8 w-10 p-0"
          onClick={() => activateYearByIndex(selectedYearIndex + 1)}
          disabled={!hasYears || !canStepNext}
          data-testid={`${testIdPrefix}-next-year`}
        >
          <span className="sr-only">{t("profile.duration.nextYear")}</span>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      {specialViews.length > 0 ? (
        <div className="flex min-w-0 gap-2 overflow-x-auto">
          {specialViews.map((view) => (
            <Button
              key={view.id}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                onPlayingChange(false)
                if (activeViewId === view.id) {
                  if (selectedYearId) {
                    onActiveViewIdChange(selectedYearId)
                  }
                  return
                }

                onActiveViewIdChange(view.id)
              }}
              className={cn(
                "shrink-0",
                activeViewId === view.id && "bg-card text-foreground",
              )}
              data-testid={view.testId}
            >
              {view.label}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
