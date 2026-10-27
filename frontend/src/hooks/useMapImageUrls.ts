import { useQuery } from "@tanstack/react-query"

import { loadMapImage } from "@/lib/map-image-graphql"
import {
  getLegacyMapImageUrls,
  getMapPreviewImageUrl,
  getWorkshopPreviewImageUrl,
  loadFirstMapImage,
} from "@/lib/map-images"

export function useMapImageUrls(
  mapName: string | null | undefined,
  workshopId?: number | string | null,
  enabled = true,
) {
  const normalizedMapName = String(mapName ?? "").trim()
  const normalizedWorkshopId = String(workshopId ?? "").trim() || null
  const imageQuery = useQuery({
    queryKey: [
      "map-image-source",
      normalizedMapName,
      normalizedWorkshopId ?? "MAP",
    ],
    queryFn: async () => {
      let urls: string[]
      try {
        const image = await loadMapImage(
          normalizedMapName,
          normalizedWorkshopId,
        )
        const primary = image.previewUrl
        urls = primary ? [primary] : []
        if (
          primary &&
          new URL(primary, window.location.origin).pathname.includes(
            "/maps/images/",
          )
        ) {
          const fallback =
            getWorkshopPreviewImageUrl(image.workshopId) ??
            getMapPreviewImageUrl(normalizedMapName)
          if (fallback) urls.push(fallback)
        }
      } catch {
        urls = getLegacyMapImageUrls(normalizedMapName, normalizedWorkshopId)
      }
      return loadFirstMapImage(urls)
    },
    enabled: enabled && normalizedMapName.length > 0,
    staleTime: 60 * 60 * 1000,
    refetchOnWindowFocus: false,
    retry: false,
  })

  return enabled && imageQuery.data ? [imageQuery.data] : []
}
