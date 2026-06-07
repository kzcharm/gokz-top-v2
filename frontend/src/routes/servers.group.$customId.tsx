import { createFileRoute } from "@tanstack/react-router"
import { useEffect } from "react"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/servers/group/$customId")({
  component: ServerGroupRoute,
  head: () => ({
    meta: [
      {
        title: getPageTitle("Server Group"),
      },
    ],
  }),
})

function ServerGroupRoute() {
  const { customId } = Route.useParams()

  useEffect(() => {
    if (customId) {
      window.scrollTo({ top: 0, left: 0 })
    }
  }, [customId])

  return null
}
