import { ChevronDownIcon } from "lucide-react"

import { TierBadge } from "@/components/Servers/TierBadge"
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

function TierSelectorValueContent({
  value,
  allLabel,
}: {
  value: TierSelectorValue
  allLabel: string
}) {
  if (value === "all") {
    return (
      <span className="truncate text-[11px] font-medium text-muted-foreground">
        {allLabel}
      </span>
    )
  }

  return <TierBadge tier={Number(value)} className="px-2 py-0.5 text-[11px]" />
}

export function TierSelector({
  value,
  onValueChange,
  allLabel = "Tier",
  className,
  triggerClassName,
  ariaLabel = "Filter by tier",
}: TierSelectorProps) {
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
          "h-8 min-w-[4.15rem] gap-1 px-1.5 text-[11px]",
          triggerClassName,
        )}
        showChevron={false}
      >
        <span className="flex w-full items-center justify-between gap-1">
          <TierSelectorValueContent value={value} allLabel={allLabel} />
          <ChevronDownIcon
            className={cn(
              "size-3.5 shrink-0 opacity-50",
              value === "all" ? "visible" : "opacity-65",
            )}
          />
        </span>
      </SelectTrigger>
      <SelectContent className={className} align="start">
        <SelectItem value="all">{allLabel}</SelectItem>
        {TIER_OPTIONS.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            <TierBadge
              tier={Number(option.value)}
              className="px-2 py-0.5 text-[11px]"
            />
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
