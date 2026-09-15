import { useQuery } from "@tanstack/react-query"

import { loadMapImage } from "@/lib/map-image-graphql"
import { getLegacyMapImageUrls, getMapImageUrl } from "@/lib/map-images"

export function useMapImageUrls(
  mapName: string | null | undefined,
  workshopId?: number | string | null,
  enabled = true,
) {
  const normalizedMapName = String(mapName ?? "").trim()
  const normalizedWorkshopId = String(workshopId ?? "").trim() || null
  const imageQuery = useQuery({
    queryKey: [
      "graphql",
      "map-image",
      normalizedMapName,
      normalizedWorkshopId ?? "MAP",
    ],
    queryFn: () => loadMapImage(normalizedMapName, normalizedWorkshopId),
    enabled: enabled && normalizedMapName.length > 0,
    staleTime: 60 * 60 * 1000,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  if (!enabled) {
    return []
  }
  if (imageQuery.isError) {
    return getLegacyMapImageUrls(normalizedMapName, normalizedWorkshopId)
  }

  return [
    getMapImageUrl(normalizedMapName),
    imageQuery.data?.previewUrl,
  ].filter((url): url is string => Boolean(url))
}
