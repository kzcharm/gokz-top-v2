import { Info } from "lucide-react"
import type { ReactElement } from "react"
import { useTranslation } from "react-i18next"

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

export function MapMetricTooltip({
  explanation,
  label,
  children,
}: {
  explanation: string
  label: string
  children: ReactElement
}) {
  const { t } = useTranslation()
  return (
    <span className="inline-flex min-w-0 items-center">
      <Tooltip delayDuration={350}>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent className="max-w-[min(22rem,calc(100vw-2rem))] text-left text-wrap">
          {explanation}
        </TooltipContent>
      </Tooltip>
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="hidden size-8 shrink-0 items-center justify-center rounded-md bg-background text-foreground [@media(pointer:coarse)]:inline-flex"
            aria-label={t("maps.metricExplanation", { metric: label })}
          >
            <Info className="size-3.5" aria-hidden="true" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="max-w-[calc(100vw-2rem)] text-sm">
          {explanation}
        </PopoverContent>
      </Popover>
    </span>
  )
}
