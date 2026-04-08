import { useQuery } from "@tanstack/react-query"

import { PlayersService } from "@/client"
import useAuth from "@/hooks/useAuth"

const UserInformation = () => {
  const { user: currentUser } = useAuth()
  const playerQuery = useQuery({
    queryKey: ["user-settings-player", currentUser?.steamid64],
    enabled: Boolean(currentUser?.steamid64),
    queryFn: () =>
      PlayersService.readPlayer({ identifier: String(currentUser?.steamid64) }),
    staleTime: 60_000,
  })

  if (!currentUser) return null

  const player = playerQuery.data

  return (
    <div className="max-w-md">
      <h3 className="text-lg font-semibold py-4">Steam Profile</h3>
      <div className="space-y-4 rounded-lg border p-4">
        <div>
          <p className="text-sm text-muted-foreground">Display name</p>
          <p className="font-medium">
            {player?.alias || player?.name || currentUser.player?.display_name || "Unknown"}
          </p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Steam ID64</p>
          <p className="font-mono text-sm">{currentUser.steamid64}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Country</p>
          <p>{player?.country || "N/A"}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Custom ID</p>
          <p>{player?.custom_id || "N/A"}</p>
        </div>
      </div>
    </div>
  )
}

export default UserInformation
