import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/maps/$mapName")({
  beforeLoad: ({ params, location }) => {
    if (location.pathname === `/maps/${params.mapName}`) {
      throw redirect({
        to: "/maps/$mapName/maptop",
        params: { mapName: params.mapName },
        search: location.search,
      })
    }
  },
})
