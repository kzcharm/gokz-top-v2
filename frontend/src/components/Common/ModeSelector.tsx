import { ChevronDownIcon } from "lucide-react"

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
  const selectedLabel =
    value === "all"
      ? allLabel
      : RECORD_MODE_OPTIONS.find((option) => option.value === value)?.label ??
        value

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
          "h-8 w-[5.1rem] min-w-[5.1rem] px-1.5 text-[11px]",
          triggerClassName,
        )}
        showChevron={false}
      >
        <span className="flex w-full items-center justify-between gap-1">
          <span className="truncate">{selectedLabel}</span>
          <ChevronDownIcon
            className={cn(
              "size-3.5 shrink-0 opacity-50",
              value === "all" ? "visible" : "invisible",
            )}
          />
        </span>
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
