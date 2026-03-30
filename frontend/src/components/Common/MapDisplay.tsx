import { cn } from "@/lib/utils"

interface MapDisplayProps {
  mapName: string | null | undefined
  className?: string
}

export function getMapImageUrl(mapName: string | null | undefined) {
  if (!mapName || mapName.trim() === "") {
    return null
  }

  return `https://github.com/KZGlobalTeam/map-images/raw/public/webp/${mapName}.webp`
}

export function MapDisplay({ mapName, className }: MapDisplayProps) {
  if (!mapName || mapName.trim() === "") {
    return <span className="text-muted-foreground">-</span>
  }

  const imageUrl = getMapImageUrl(mapName)

  return (
    <div
      className={cn(
        "relative h-10 w-56 overflow-hidden rounded-md bg-gray-100 dark:bg-gray-800",
        className,
      )}
      style={
        imageUrl
          ? {
              backgroundImage: `url(${imageUrl})`,
              backgroundPosition: "center",
              backgroundSize: "cover",
            }
          : undefined
      }
    >
      <span className="absolute inset-0 flex items-center justify-center bg-black/30 px-2 py-1 text-sm font-medium text-white drop-shadow-lg [text-shadow:_0_1px_2px_rgb(0_0_0_/_0.8)]">
        {mapName}
      </span>
    </div>
  )
}
