import { ReactQueryDevtools } from "@tanstack/react-query-devtools"
import {
  createRootRoute,
  HeadContent,
  Outlet,
  useRouterState,
} from "@tanstack/react-router"
import { TanStackRouterDevtools } from "@tanstack/react-router-devtools"
import { AnalyticsConsentBanner } from "@/components/Common/AnalyticsConsentBanner"
import { AnalyticsPageViewSync } from "@/components/Common/AnalyticsPageViewSync"
import ErrorComponent from "@/components/Common/ErrorComponent"
import NotFound from "@/components/Common/NotFound"
import { DocumentTitleSync } from "@/i18n/document-title"
import { isPlayerCardPath } from "@/lib/card-route"

export const Route = createRootRoute({
  component: RootComponent,
  notFoundComponent: () => <NotFound />,
  errorComponent: ({ error }) => <ErrorComponent error={error} />,
})

function RootComponent() {
  const isCard = useRouterState({
    select: (state) => isPlayerCardPath(state.location.pathname),
  })
  return (
    <>
      <HeadContent />
      <DocumentTitleSync />
      {!isCard && <AnalyticsPageViewSync />}
      <Outlet />
      {!isCard && <AnalyticsConsentBanner />}
      {!isCard && <TanStackRouterDevtools position="bottom-right" />}
      {!isCard && <ReactQueryDevtools initialIsOpen={false} />}
    </>
  )
}
