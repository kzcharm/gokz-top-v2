import { ChevronDown } from "lucide-react"

import { useScope, type AppScope } from "@/components/scope-provider"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

const SCOPE_OPTIONS: Array<{
  description: string
  toneClassName: string
  value: AppScope
}> = [
  {
    description: "Overall leaderboard scope",
    toneClassName:
      "border-transparent bg-slate-800 text-slate-50 dark:bg-slate-100 dark:text-slate-900",
    value: "OVR",
  },
  {
    description: "KZTimer scope",
    toneClassName:
      "border-transparent bg-sky-600 text-white dark:bg-sky-500 dark:text-slate-950",
    value: "KZT",
  },
  {
    description: "SimpleKZ scope",
    toneClassName:
      "border-transparent bg-emerald-600 text-white dark:bg-emerald-500 dark:text-slate-950",
    value: "SKZ",
  },
  {
    description: "Vanilla scope",
    toneClassName:
      "border-transparent bg-amber-500 text-slate-950 dark:bg-amber-400 dark:text-slate-950",
    value: "VNL",
  },
]

function getScopeTone(scope: AppScope) {
  return (
    SCOPE_OPTIONS.find((option) => option.value === scope)?.toneClassName ??
    SCOPE_OPTIONS[0].toneClassName
  )
}

export function ScopeSelector() {
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
          aria-label="Select record scope"
        >
          <span>{scope}</span>
          <ChevronDown className="size-3.5 opacity-75" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44">
        <DropdownMenuRadioGroup
          value={scope}
          onValueChange={(value) => setScope(value as AppScope)}
        >
          {SCOPE_OPTIONS.map((option) => (
            <DropdownMenuRadioItem key={option.value} value={option.value}>
              <span
                aria-hidden="true"
                className={cn(
                  "inline-flex min-w-11 items-center justify-center rounded-md px-2 py-0.5 font-mono text-xs font-semibold tracking-[0.16em]",
                  option.toneClassName,
                )}
              >
                {option.value}
              </span>
              <span className="text-xs text-muted-foreground">
                {option.description}
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
