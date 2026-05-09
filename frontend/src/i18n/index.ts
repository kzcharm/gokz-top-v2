import i18n from "i18next"
import { initReactI18next } from "react-i18next"

import { resources } from "@/i18n/resources"

export const SUPPORTED_LOCALES = ["en", "zh-CN", "ru"] as const
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]

export const DEFAULT_LOCALE: SupportedLocale = "en"
export const LANGUAGE_STORAGE_KEY = "gokz-language"

export function normalizeLocale(
  value: string | null | undefined,
): SupportedLocale {
  if (!value) {
    return DEFAULT_LOCALE
  }

  const normalized = value.toLowerCase()

  if (normalized.startsWith("zh")) {
    return "zh-CN"
  }

  if (normalized.startsWith("ru")) {
    return "ru"
  }

  return "en"
}

export function getInitialLocale() {
  if (typeof window === "undefined") {
    return DEFAULT_LOCALE
  }

  const storedLocale = localStorage.getItem(LANGUAGE_STORAGE_KEY)
  if (storedLocale) {
    return normalizeLocale(storedLocale)
  }

  return normalizeLocale(navigator.language)
}

void i18n.use(initReactI18next).init({
  resources,
  lng: getInitialLocale(),
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: [...SUPPORTED_LOCALES],
  interpolation: {
    escapeValue: false,
  },
})

i18n.on("languageChanged", (language) => {
  if (typeof window !== "undefined") {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, normalizeLocale(language))
  }
})

export function getCurrentLocale(): SupportedLocale {
  return normalizeLocale(i18n.resolvedLanguage ?? i18n.language)
}

export function getCurrentLanguageLabel() {
  return i18n.t(`language.options.${getCurrentLocale()}`)
}

export function setLocale(locale: SupportedLocale) {
  return i18n.changeLanguage(locale)
}

export default i18n
