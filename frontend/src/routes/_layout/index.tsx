import { createFileRoute } from "@tanstack/react-router"

import useAuth from "@/hooks/useAuth"
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
  const { user: currentUser } = useAuth()
  const displayName =
    currentUser?.player?.name || `Player ${currentUser?.steamid64 ?? ""}`

  return (
    <div>
      <div>
        <h1 className="text-2xl truncate max-w-sm">Hi, {displayName} 👋</h1>
        <p className="text-muted-foreground">
          Welcome back, nice to see you again!!!
        </p>
      </div>
    </div>
  )
}
