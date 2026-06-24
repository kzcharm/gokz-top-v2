import { ChevronDownIcon } from "lucide-react"
import { useTranslation } from "react-i18next"

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
  showAllLabelInTrigger?: boolean
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
  allLabel,
  noneLabel,
  includeAll = true,
  includeNone = false,
  disabled = false,
  className,
  triggerClassName,
  ariaLabel,
  showAllLabelInTrigger = false,
}: TierSelectorProps) {
  const { t } = useTranslation()
  const resolvedAllLabel = allLabel ?? t("common.tier")
  const resolvedNoneLabel = noneLabel ?? t("common.none")
  const resolvedAriaLabel = ariaLabel ?? t("maps.filterTier")
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
        aria-label={resolvedAriaLabel}
        className={cn(
          "h-8 w-11 min-w-11 px-1 text-[11px]",
          showAllLabelInTrigger ? "justify-between px-3" : "justify-center",
          triggerClassName,
        )}
        showChevron={showAllLabelInTrigger}
      >
        {isAllSelected ? (
          showAllLabelInTrigger ? (
            <span>{resolvedAllLabel}</span>
          ) : (
            <ChevronDownIcon className="size-3.5 shrink-0 opacity-50" />
          )
        ) : (
          <TierSelectorValueContent
            value={value}
            noneLabel={resolvedNoneLabel}
          />
        )}
      </SelectTrigger>
      <SelectContent className={className} align="start">
        {includeAll ? (
          <SelectItem value="all">{resolvedAllLabel}</SelectItem>
        ) : null}
        {includeNone ? (
          <SelectItem value="none">{resolvedNoneLabel}</SelectItem>
        ) : null}
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
