import { createFileRoute } from "@tanstack/react-router"

import { MediaPage } from "@/components/Media/MediaPage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/media")({
  component: MediaPage,
  head: () => ({ meta: [{ title: getPageTitle("Media") }] }),
})
