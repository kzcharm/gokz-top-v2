import useAuth from "@/hooks/useAuth"

const UserInformation = () => {
  const { user: currentUser } = useAuth()

  if (!currentUser) return null

  return (
    <div className="max-w-md">
      <h3 className="text-lg font-semibold py-4">Steam Profile</h3>
      <div className="space-y-4 rounded-lg border p-4">
        <div>
          <p className="text-sm text-muted-foreground">Display name</p>
          <p className="font-medium">{currentUser.player?.name || "Unknown"}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Steam ID64</p>
          <p className="font-mono text-sm">{currentUser.steamid64}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Country</p>
          <p>{currentUser.player?.country || "N/A"}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Custom ID</p>
          <p>{currentUser.player?.custom_id || "N/A"}</p>
        </div>
      </div>
    </div>
  )
}

export default UserInformation
