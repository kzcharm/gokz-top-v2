import { useCallback } from "react"
import { useTranslation } from "react-i18next"

import {
  getCurrentLanguageLabel,
  normalizeLocale,
  type SupportedLocale,
  setLocale,
} from "@/i18n"

export function useLocale() {
  const { i18n } = useTranslation()

  const changeLocale = useCallback(async (locale: SupportedLocale) => {
    await setLocale(locale)
  }, [])

  return {
    locale: normalizeLocale(i18n.resolvedLanguage),
    changeLocale,
    currentLanguageLabel: getCurrentLanguageLabel(),
  }
}
