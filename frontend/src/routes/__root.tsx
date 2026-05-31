import { ReactQueryDevtools } from "@tanstack/react-query-devtools"
import { createRootRoute, HeadContent, Outlet } from "@tanstack/react-router"
import { TanStackRouterDevtools } from "@tanstack/react-router-devtools"
import { AnalyticsConsentBanner } from "@/components/Common/AnalyticsConsentBanner"
import { AnalyticsPageViewSync } from "@/components/Common/AnalyticsPageViewSync"
import ErrorComponent from "@/components/Common/ErrorComponent"
import NotFound from "@/components/Common/NotFound"
import { DocumentTitleSync } from "@/i18n/document-title"

export const Route = createRootRoute({
  component: () => (
    <>
      <HeadContent />
      <DocumentTitleSync />
      <AnalyticsPageViewSync />
      <Outlet />
      <AnalyticsConsentBanner />
      <TanStackRouterDevtools position="bottom-right" />
      <ReactQueryDevtools initialIsOpen={false} />
    </>
  ),
  notFoundComponent: () => <NotFound />,
  errorComponent: () => <ErrorComponent />,
})
