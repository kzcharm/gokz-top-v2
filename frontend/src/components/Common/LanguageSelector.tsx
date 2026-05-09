import { Check, Languages } from "lucide-react"
import { useTranslation } from "react-i18next"

import { CountryFlag } from "@/components/Common/CountryFlag"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { SupportedLocale } from "@/i18n"
import { useLocale } from "@/i18n/use-locale"

const LANGUAGE_OPTIONS: Array<{
  countryCode: string
  value: SupportedLocale
}> = [
  { countryCode: "GB", value: "en" },
  { countryCode: "CN", value: "zh-CN" },
  { countryCode: "RU", value: "ru" },
]

export function LanguageSelector() {
  const { t } = useTranslation()
  const { locale, changeLocale, currentLanguageLabel } = useLocale()
  const language = locale ?? "en"

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-foreground"
          aria-label={`${t("language.select")}. ${t("language.current", {
            language: currentLanguageLabel,
          })}`}
        >
          <Languages className="size-[1.2rem]" />
          <span className="sr-only">{t("language.select")}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        {LANGUAGE_OPTIONS.map((option) => (
          <DropdownMenuItem
            key={option.value}
            onSelect={() => {
              void changeLocale(option.value)
            }}
          >
            <CountryFlag countryCode={option.countryCode} showTooltip={false} />
            <span className="flex-1">
              {t(`language.options.${option.value}`)}
            </span>
            {language === option.value ? (
              <Check className="text-foreground size-4" />
            ) : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
