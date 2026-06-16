import {
  createFileRoute,
  Link,
  Outlet,
  redirect,
  useRouterState,
} from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/dashboard")({
  beforeLoad: ({ location }) => {
    if (location.pathname === "/dashboard") {
      throw redirect({
        to: "/dashboard/records",
      })
    }
  },
  component: DashboardLayout,
  head: () => ({
    meta: [
      {
        title: getPageTitle(),
      },
    ],
  }),
})

function DashboardLayout() {
  const { t } = useTranslation()
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const tabValue = pathname.startsWith("/dashboard/reviews")
    ? "reviews"
    : "records"

  return (
    <Tabs value={tabValue} className="flex flex-col gap-6">
      <TabsList className="w-fit border border-border bg-background/60">
        <TabsTrigger value="records" asChild>
          <Link to="/dashboard/records">{t("dashboard.records")}</Link>
        </TabsTrigger>
        <TabsTrigger value="reviews" asChild>
          <Link to="/dashboard/reviews">{t("dashboard.reviews")}</Link>
        </TabsTrigger>
      </TabsList>
      <Outlet />
    </Tabs>
  )
}
