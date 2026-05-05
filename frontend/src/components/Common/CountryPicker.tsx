import { Check, ChevronDown, X } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { CountryFlag, countryOptions, getCountryName } from "./CountryFlag"

interface CountryPickerProps {
  value: string | null
  onChange: (value: string | null) => void
  placeholder?: string
  clearLabel?: string
  className?: string
  triggerClassName?: string
  disabled?: boolean
}

export function CountryPicker({
  value,
  onChange,
  placeholder = "Select a place",
  clearLabel = "Clear selection",
  className,
  triggerClassName,
  disabled = false,
}: CountryPickerProps) {
  const [query, setQuery] = useState("")
  const [open, setOpen] = useState(false)
  const searchRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      searchRef.current?.focus()
    }, 0)

    return () => window.clearTimeout(timeoutId)
  }, [open])

  const filteredCountries = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (normalizedQuery.length === 0) {
      return countryOptions
    }

    return countryOptions.filter((option) => {
      return (
        option.countryCode.toLowerCase().includes(normalizedQuery) ||
        option.name.toLowerCase().includes(normalizedQuery)
      )
    })
  }, [query])

  return (
    <DropdownMenu
      modal={false}
      open={open && !disabled}
      onOpenChange={(nextOpen) => setOpen(disabled ? false : nextOpen)}
    >
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "border-input data-[state=open]:bg-accent/50 focus-visible:border-ring focus-visible:ring-ring/50 flex h-9 w-full items-center justify-between rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow,background-color] focus-visible:ring-[3px]",
            open && "border-ring ring-ring/50 ring-[3px]",
            disabled && "cursor-not-allowed opacity-50",
            triggerClassName,
          )}
          data-state={open ? "open" : "closed"}
          disabled={disabled}
        >
          <span className="flex min-w-0 items-center gap-2">
            {value ? (
              <>
                <CountryFlag countryCode={value} showTooltip={false} />
                <span className="truncate">
                  {getCountryName(value) || value}
                </span>
              </>
            ) : (
              <span className="text-muted-foreground">{placeholder}</span>
            )}
          </span>
          <ChevronDown className="text-muted-foreground size-4 shrink-0" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        avoidCollisions={false}
        className={cn(
          "w-[var(--radix-dropdown-menu-trigger-width)] overflow-hidden rounded-xl p-0",
          className,
        )}
        side="bottom"
        sideOffset={8}
      >
        <div className="border-b p-3">
          <Input
            ref={searchRef}
            value={query}
            maxLength={50}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => event.stopPropagation()}
            placeholder="Search a place"
          />
        </div>
        <div className="max-h-72 overflow-y-auto py-1">
          <button
            type="button"
            className="hover:bg-accent hover:text-accent-foreground flex w-full items-center gap-3 px-3 py-2 text-left text-sm"
            onClick={() => {
              onChange(null)
              setOpen(false)
              setQuery("")
            }}
          >
            <X className="text-muted-foreground size-4" />
            <span>{clearLabel}</span>
          </button>
          {filteredCountries.map((option) => {
            const selected = value === option.countryCode
            return (
              <button
                key={option.countryCode}
                type="button"
                className={cn(
                  "hover:bg-accent hover:text-accent-foreground flex w-full items-center gap-3 px-3 py-2 text-left text-sm",
                  selected && "text-primary",
                )}
                onClick={() => {
                  onChange(option.countryCode)
                  setOpen(false)
                  setQuery("")
                }}
              >
                <CountryFlag
                  countryCode={option.countryCode}
                  showTooltip={false}
                />
                <span className="min-w-0 flex-1 truncate">{option.name}</span>
                {selected ? <Check className="size-4 shrink-0" /> : null}
              </button>
            )
          })}
          {filteredCountries.length === 0 ? (
            <div className="text-muted-foreground px-3 py-6 text-sm">
              No matches found.
            </div>
          ) : null}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
