export const GOOGLE_ANALYTICS_ID = "G-SD145MZQDR"
export const ANALYTICS_CONSENT_STORAGE_KEY = "gokz-analytics-consent"
export const ANALYTICS_CONSENT_ACCEPTED = "v1:accepted"
export const ANALYTICS_CONSENT_REJECTED = "v1:rejected"
export const ANALYTICS_CONSENT_CHANGED_EVENT = "gokz:analytics-consent-changed"
export const ANALYTICS_CONSENT_PREVIEW_PARAM = "analytics-consent-preview"
export const ANALYTICS_CONSENT_PREVIEW_STORAGE_KEY =
  "gokz-analytics-consent-preview"

type GtagCommand = "consent" | "config" | "event" | "js"
type Gtag = (
  command: GtagCommand,
  target: string | Date,
  params?: Record<string, unknown>,
) => void

declare global {
  interface Window {
    dataLayer?: unknown[]
    gtag?: Gtag
    previewAnalyticsConsentBanner?: () => void
  }
}

let initialized = false
let scriptRequested = false
let defaultConsentInitialized = false

function getStoredConsent() {
  if (typeof window === "undefined") {
    return null
  }

  const value = window.localStorage.getItem(ANALYTICS_CONSENT_STORAGE_KEY)

  return value === ANALYTICS_CONSENT_ACCEPTED ||
    value === ANALYTICS_CONSENT_REJECTED
    ? value
    : null
}

function setStoredConsent(value: string) {
  window.localStorage.setItem(ANALYTICS_CONSENT_STORAGE_KEY, value)
  window.dispatchEvent(new Event(ANALYTICS_CONSENT_CHANGED_EVENT))
}

function ensureGtag() {
  window.dataLayer = window.dataLayer ?? []
  const fallbackGtag: Gtag = (...args: Parameters<Gtag>) => {
    window.dataLayer?.push(args)
  }
  window.gtag = window.gtag ?? fallbackGtag

  return window.gtag
}

export function initializeAnalyticsConsentDefaults() {
  if (typeof window === "undefined" || defaultConsentInitialized) {
    return
  }

  const gtag = ensureGtag()
  gtag("consent", "default", {
    ad_personalization: "denied",
    ad_storage: "denied",
    ad_user_data: "denied",
    analytics_storage: "denied",
  })
  defaultConsentInitialized = true
}

export function isAnalyticsConsentAccepted() {
  return getStoredConsent() === ANALYTICS_CONSENT_ACCEPTED
}

export function isAnalyticsConsentRejected() {
  return getStoredConsent() === ANALYTICS_CONSENT_REJECTED
}

export function hasAnalyticsConsentChoice() {
  return getStoredConsent() !== null
}

export function acceptAnalyticsConsent() {
  if (typeof window === "undefined") {
    return
  }

  setStoredConsent(ANALYTICS_CONSENT_ACCEPTED)
}

export function rejectAnalyticsConsent() {
  if (typeof window === "undefined") {
    return
  }

  setStoredConsent(ANALYTICS_CONSENT_REJECTED)
}

export function clearAnalyticsConsent() {
  if (typeof window === "undefined") {
    return
  }

  window.localStorage.removeItem(ANALYTICS_CONSENT_STORAGE_KEY)
  window.dispatchEvent(new Event(ANALYTICS_CONSENT_CHANGED_EVENT))
}

export function shouldShowAnalyticsConsentBanner() {
  if (typeof window === "undefined" || hasAnalyticsConsentChoice()) {
    return false
  }

  return import.meta.env.PROD || isAnalyticsConsentPreviewEnabled()
}

export function isAnalyticsConsentPreviewEnabled() {
  if (typeof window === "undefined" || !import.meta.env.DEV) {
    return false
  }

  const params = new URLSearchParams(window.location.search)
  if (params.get(ANALYTICS_CONSENT_PREVIEW_PARAM) === "1") {
    window.localStorage.setItem(ANALYTICS_CONSENT_PREVIEW_STORAGE_KEY, "1")
    return true
  }

  return (
    window.localStorage.getItem(ANALYTICS_CONSENT_PREVIEW_STORAGE_KEY) === "1"
  )
}

export function enableAnalyticsConsentPreview() {
  if (typeof window === "undefined" || !import.meta.env.DEV) {
    return
  }

  window.localStorage.setItem(ANALYTICS_CONSENT_PREVIEW_STORAGE_KEY, "1")
  clearAnalyticsConsent()
}

export function bootstrapAnalyticsConsentPreview() {
  if (typeof window === "undefined" || !import.meta.env.DEV) {
    return
  }

  registerAnalyticsConsentPreviewHelper()

  const params = new URLSearchParams(window.location.search)
  if (params.get(ANALYTICS_CONSENT_PREVIEW_PARAM) === "1") {
    enableAnalyticsConsentPreview()
  }
}

export function registerAnalyticsConsentPreviewHelper() {
  if (typeof window === "undefined" || !import.meta.env.DEV) {
    return
  }

  window.previewAnalyticsConsentBanner = enableAnalyticsConsentPreview
}

function injectGoogleAnalyticsScript() {
  if (scriptRequested || document.querySelector("script[data-gokz-ga]")) {
    scriptRequested = true
    return
  }

  const script = document.createElement("script")
  script.async = true
  script.dataset.gokzGa = "true"
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(
    GOOGLE_ANALYTICS_ID,
  )}`
  document.head.appendChild(script)
  scriptRequested = true
}

export function initializeGoogleAnalytics() {
  if (typeof window === "undefined") {
    return false
  }

  initializeAnalyticsConsentDefaults()

  if (!import.meta.env.PROD || !isAnalyticsConsentAccepted()) {
    return false
  }

  const gtag = ensureGtag()
  gtag("consent", "update", {
    analytics_storage: "granted",
  })

  injectGoogleAnalyticsScript()

  if (!initialized) {
    gtag("js", new Date())
    gtag("config", GOOGLE_ANALYTICS_ID, {
      send_page_view: false,
    })
    initialized = true
  }

  return true
}

export function trackPageView(path: string) {
  if (typeof window === "undefined" || !initializeGoogleAnalytics()) {
    return
  }

  window.gtag?.("event", "page_view", {
    page_location: window.location.href,
    page_path: path,
    page_title: document.title,
  })
}
