import { Check, ChevronsUpDown } from "lucide-react"
import { useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

export function BrandSelector({
  id,
  brands,
  value,
  onChange,
}: {
  id: string
  brands: string[]
  value: string
  onChange: (value: string) => void
}) {
  const { t } = useTranslation()
  const listId = useId()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const options = [
    { value: "__other__", label: t("gear.otherBrand") },
    ...brands
      .filter((name) =>
        name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()),
      )
      .map((name) => ({ value: name, label: name })),
  ]
  const select = (selected: string) => {
    onChange(selected)
    setOpen(false)
  }
  return (
    <Popover
      open={open}
      onOpenChange={(value) => {
        setOpen(value)
        setQuery("")
        setActive(0)
      }}
    >
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-required="true"
          aria-expanded={open}
          aria-controls={listId}
          className="w-full justify-between"
        >
          {value === "__other__"
            ? t("gear.otherBrand")
            : value || t("gear.selectBrand")}
          <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[var(--radix-popover-trigger-width)] p-2"
        align="start"
      >
        <Input
          aria-label={t("gear.searchBrand")}
          placeholder={t("gear.searchBrand")}
          value={query}
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={`${listId}-${active}`}
          onChange={(event) => {
            setQuery(event.target.value)
            setActive(0)
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault()
              setActive((i) => Math.min(i + 1, options.length - 1))
            }
            if (event.key === "ArrowUp") {
              event.preventDefault()
              setActive((i) => Math.max(i - 1, 0))
            }
            if (event.key === "Enter") {
              event.preventDefault()
              select(options[active].value)
            }
          }}
        />
        <div
          id={listId}
          role="listbox"
          aria-label={t("gear.brand")}
          className="mt-2 max-h-56 overflow-y-auto"
        >
          {options.map((option, index) => (
            <button
              key={option.value}
              id={`${listId}-${index}`}
              type="button"
              role="option"
              aria-selected={active === index}
              className="flex w-full items-center justify-between rounded px-2 py-2 text-left text-sm hover:bg-accent aria-selected:bg-accent"
              onClick={() => select(option.value)}
            >
              {option.label}
              {value === option.value ? <Check className="size-4" /> : null}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
