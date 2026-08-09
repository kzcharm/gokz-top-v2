import { createFileRoute } from "@tanstack/react-router"

import { CountriesLeaderboardTab } from "@/components/Leaderboards/CountriesLeaderboardTab"

export const Route = createFileRoute("/_layout/leaderboards/countries")({
  component: CountriesRoute,
})

function CountriesRoute() {
  return <CountriesLeaderboardTab />
}
