import { ChevronDownIcon } from "lucide-react"

import { TierBadge } from "@/components/Servers/TierBadge"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

export type TierSelectorValue = `${number}` | "all" | "none"

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
  noneLabel?: string
  includeAll?: boolean
  includeNone?: boolean
  disabled?: boolean
  className?: string
  triggerClassName?: string
  ariaLabel?: string
}

function TierSelectorValueContent({
  value,
  noneLabel,
}: {
  value: TierSelectorValue
  noneLabel: string
}) {
  if (value === "all") {
    return null
  }

  if (value === "none") {
    return (
      <Badge
        variant="outline"
        className="border-border bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
      >
        {noneLabel}
      </Badge>
    )
  }

  return <TierBadge tier={Number(value)} className="px-2 py-0.5 text-[11px]" />
}

export function TierSelector({
  value,
  onValueChange,
  allLabel = "Tier",
  noneLabel = "None",
  includeAll = true,
  includeNone = false,
  disabled = false,
  className,
  triggerClassName,
  ariaLabel = "Filter by tier",
}: TierSelectorProps) {
  const isAllSelected = includeAll && value === "all"

  return (
    <Select
      value={value}
      disabled={disabled}
      onValueChange={(nextValue) =>
        onValueChange(nextValue as TierSelectorValue)
      }
    >
      <SelectTrigger
        aria-label={ariaLabel}
        className={cn(
          "h-8 w-11 min-w-11 justify-center px-1 text-[11px]",
          triggerClassName,
        )}
        showChevron={false}
      >
        {isAllSelected ? (
          <ChevronDownIcon className="size-3.5 shrink-0 opacity-50" />
        ) : (
          <TierSelectorValueContent value={value} noneLabel={noneLabel} />
        )}
      </SelectTrigger>
      <SelectContent className={className} align="start">
        {includeAll ? <SelectItem value="all">{allLabel}</SelectItem> : null}
        {includeNone ? <SelectItem value="none">{noneLabel}</SelectItem> : null}
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
