import { createFileRoute } from "@tanstack/react-router"

import { RecentRecordsPanel } from "@/components/Records/RecentRecordsPanel"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: getPageTitle(),
      },
    ],
  }),
})

function Dashboard() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Follow the latest runs as they land across the platform.
        </p>
      </div>

      <Tabs defaultValue="records" className="flex flex-col gap-4">
        <TabsList className="w-fit">
          <TabsTrigger value="records">Records</TabsTrigger>
        </TabsList>
        <TabsContent value="records" className="mt-0">
          <RecentRecordsPanel />
        </TabsContent>
      </Tabs>
    </div>
  )
}
