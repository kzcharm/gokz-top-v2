import { ChevronDownIcon } from "lucide-react"

import { ModeBadge } from "@/components/Records/ModeBadge"
import { RECORD_MODE_OPTIONS, type RecordMode } from "@/components/Records/mode"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

export type ModeSelectorValue = RecordMode | "all"

interface ModeSelectorProps {
  value: ModeSelectorValue
  onValueChange: (value: ModeSelectorValue) => void
  allLabel?: string
  className?: string
  triggerClassName?: string
  ariaLabel?: string
}

export function ModeSelector({
  value,
  onValueChange,
  allLabel = "All modes",
  className,
  triggerClassName,
  ariaLabel = "Filter by mode",
}: ModeSelectorProps) {
  const isAllSelected = value === "all"
  const selectedLabel = isAllSelected
    ? allLabel
    : (RECORD_MODE_OPTIONS.find((option) => option.value === value)?.label ??
      value)

  return (
    <Select
      value={value}
      onValueChange={(nextValue) =>
        onValueChange(nextValue as ModeSelectorValue)
      }
    >
      <SelectTrigger
        aria-label={ariaLabel}
        className={cn(
          "h-8 w-12 min-w-12 justify-center px-1 text-[11px]",
          triggerClassName,
        )}
        showChevron={false}
      >
        {isAllSelected ? (
          <ChevronDownIcon className="size-3.5 shrink-0 opacity-50" />
        ) : (
          <ModeBadge mode={selectedLabel} className="w-full px-0 text-[11px]" />
        )}
      </SelectTrigger>
      <SelectContent className={className} align="start">
        <SelectItem value="all">{allLabel}</SelectItem>
        {RECORD_MODE_OPTIONS.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
