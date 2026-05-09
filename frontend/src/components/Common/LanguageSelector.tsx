import { Check, Languages } from "lucide-react"
import { useState } from "react"

import { CountryFlag } from "@/components/Common/CountryFlag"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

type PlaceholderLanguage = "en" | "zh" | "ru"

const LANGUAGE_OPTIONS: Array<{
  countryCode: string
  label: string
  value: PlaceholderLanguage
}> = [
  { countryCode: "GB", label: "English", value: "en" },
  { countryCode: "CN", label: "Chinese", value: "zh" },
  { countryCode: "RU", label: "Russian", value: "ru" },
]

export function LanguageSelector() {
  const [language, setLanguage] = useState<PlaceholderLanguage>("en")

  const currentLanguage =
    LANGUAGE_OPTIONS.find((option) => option.value === language)?.label ??
    "English"

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-foreground"
          aria-label={`Select language. Current language: ${currentLanguage}.`}
        >
          <Languages className="size-[1.2rem]" />
          <span className="sr-only">Select language</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        {LANGUAGE_OPTIONS.map((option) => (
          <DropdownMenuItem
            key={option.value}
            onSelect={() => setLanguage(option.value)}
          >
            <CountryFlag countryCode={option.countryCode} showTooltip={false} />
            <span className="flex-1">{option.label}</span>
            {language === option.value ? (
              <Check className="text-foreground size-4" />
            ) : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
