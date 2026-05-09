import { ChevronDown } from "lucide-react"
import { useTranslation } from "react-i18next"

import { type AppScope, useScope } from "@/components/scope-provider"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

export const SCOPE_OPTIONS: Array<{
  toneClassName: string
  value: AppScope
}> = [
  {
    toneClassName:
      "border-transparent bg-slate-800 text-slate-50 dark:bg-slate-100 dark:text-slate-900",
    value: "OVR",
  },
  {
    toneClassName:
      "border-transparent bg-sky-600 text-white dark:bg-sky-500 dark:text-slate-950",
    value: "KZT",
  },
  {
    toneClassName:
      "border-transparent bg-emerald-600 text-white dark:bg-emerald-500 dark:text-slate-950",
    value: "SKZ",
  },
  {
    toneClassName:
      "border-transparent bg-amber-500 text-slate-950 dark:bg-amber-400 dark:text-slate-950",
    value: "VNL",
  },
]

export function getScopeTone(scope: AppScope) {
  return (
    SCOPE_OPTIONS.find((option) => option.value === scope)?.toneClassName ??
    SCOPE_OPTIONS[0].toneClassName
  )
}

export function ScopeSelector() {
  const { t } = useTranslation()
  const { scope, setScope } = useScope()

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className={cn(
            "h-9 min-w-20 gap-2 rounded-full px-3 font-mono font-semibold tracking-[0.16em] shadow-xs",
            getScopeTone(scope),
          )}
          aria-label={t("scope.select")}
        >
          <span>{scope}</span>
          <ChevronDown className="size-3.5 opacity-75" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-28">
        <DropdownMenuRadioGroup
          value={scope}
          onValueChange={(value) => setScope(value as AppScope)}
        >
          {SCOPE_OPTIONS.map((option) => (
            <DropdownMenuRadioItem key={option.value} value={option.value}>
              <span
                className={cn(
                  "inline-flex min-w-12 items-center justify-center rounded-md px-2 py-0.5 font-mono text-xs font-semibold tracking-[0.16em]",
                  option.toneClassName,
                )}
              >
                {option.value}
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
