import { createFileRoute } from "@tanstack/react-router"
import { GearLeaderboard } from "@/components/Gear/GearLeaderboard"
export const Route = createFileRoute("/_layout/leaderboards/gear")({
  component: GearLeaderboard,
})
