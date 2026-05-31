import { useRouterState } from "@tanstack/react-router"
import { useEffect } from "react"

import {
  ANALYTICS_CONSENT_CHANGED_EVENT,
  initializeAnalyticsConsentDefaults,
  trackPageView,
} from "@/lib/google-analytics"

export function AnalyticsPageViewSync() {
  const href = useRouterState({
    select: (state) => state.location.href,
  })

  useEffect(() => {
    initializeAnalyticsConsentDefaults()
  }, [])

  useEffect(() => {
    trackPageView(href)
  }, [href])

  useEffect(() => {
    const trackCurrentPage = () => {
      trackPageView(window.location.pathname + window.location.search)
    }

    window.addEventListener(ANALYTICS_CONSENT_CHANGED_EVENT, trackCurrentPage)

    return () => {
      window.removeEventListener(
        ANALYTICS_CONSENT_CHANGED_EVENT,
        trackCurrentPage,
      )
    }
  }, [])

  return null
}
