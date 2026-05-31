import { Check, X } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  ANALYTICS_CONSENT_CHANGED_EVENT,
  acceptAnalyticsConsent,
  initializeGoogleAnalytics,
  isAnalyticsConsentPreviewEnabled,
  registerAnalyticsConsentPreviewHelper,
  rejectAnalyticsConsent,
  shouldShowAnalyticsConsentBanner,
} from "@/lib/google-analytics"

export function AnalyticsConsentBanner() {
  const { t } = useTranslation()
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    registerAnalyticsConsentPreviewHelper()

    const syncVisibility = () => {
      setIsVisible(shouldShowAnalyticsConsentBanner())
    }

    syncVisibility()
    window.addEventListener(ANALYTICS_CONSENT_CHANGED_EVENT, syncVisibility)
    const intervalId = isAnalyticsConsentPreviewEnabled()
      ? window.setInterval(syncVisibility, 500)
      : null

    return () => {
      window.removeEventListener(
        ANALYTICS_CONSENT_CHANGED_EVENT,
        syncVisibility,
      )
      if (intervalId !== null) {
        window.clearInterval(intervalId)
      }
    }
  }, [])

  if (!isVisible) {
    return null
  }

  const accept = () => {
    acceptAnalyticsConsent()
    initializeGoogleAnalytics()
    setIsVisible(false)
  }

  const reject = () => {
    rejectAnalyticsConsent()
    setIsVisible(false)
  }

  return (
    <div className="fixed right-0 bottom-0 left-0 z-50 px-3 pb-3 sm:px-4 sm:pb-4">
      <section
        aria-labelledby="analytics-consent-title"
        className="mx-auto flex max-w-4xl flex-col gap-3 rounded-lg border bg-background/95 p-4 text-foreground shadow-lg backdrop-blur md:flex-row md:items-center md:justify-between"
      >
        <div className="min-w-0">
          <h2
            id="analytics-consent-title"
            className="font-medium text-sm leading-5"
          >
            {t("analyticsConsent.message")}
          </h2>
        </div>
        <div className="flex shrink-0 flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            size="sm"
            onClick={reject}
            className="bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/30"
          >
            <X aria-hidden="true" />
            {t("analyticsConsent.reject")}
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={accept}
            className="bg-emerald-600 text-white hover:bg-emerald-700 focus-visible:ring-emerald-500/30 dark:bg-emerald-600 dark:hover:bg-emerald-500"
          >
            <Check aria-hidden="true" />
            {t("analyticsConsent.accept")}
          </Button>
        </div>
      </section>
    </div>
  )
}
