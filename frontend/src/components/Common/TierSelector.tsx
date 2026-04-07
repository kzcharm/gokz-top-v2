import { ChevronDownIcon } from "lucide-react"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

export type TierSelectorValue = `${number}` | "all"

const TIER_OPTIONS = Array.from({ length: 8 }, (_, index) => {
  const tier = index + 1

  return {
    label: `T${tier}`,
    value: String(tier) as `${number}`,
  }
})

interface TierSelectorProps {
  value: TierSelectorValue
  onValueChange: (value: TierSelectorValue) => void
  allLabel?: string
  className?: string
  triggerClassName?: string
  ariaLabel?: string
}

export function TierSelector({
  value,
  onValueChange,
  allLabel = "All tiers",
  className,
  triggerClassName,
  ariaLabel = "Filter by tier",
}: TierSelectorProps) {
  const selectedLabel =
    value === "all"
      ? allLabel
      : (TIER_OPTIONS.find((option) => option.value === value)?.label ?? value)

  return (
    <Select
      value={value}
      onValueChange={(nextValue) =>
        onValueChange(nextValue as TierSelectorValue)
      }
    >
      <SelectTrigger
        aria-label={ariaLabel}
        className={cn(
          "h-8 w-[4.6rem] min-w-[4.6rem] px-1.5 text-[11px]",
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
        {TIER_OPTIONS.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
