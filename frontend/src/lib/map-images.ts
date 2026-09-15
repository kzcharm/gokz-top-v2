import { OpenAPI } from "@/client/core/OpenAPI"

export function getMapImageUrl(mapName: string | null | undefined) {
  if (!mapName || mapName.trim() === "") {
    return null
  }

  return `https://github.com/KZGlobalTeam/map-images/raw/public/webp/${mapName}.webp`
}

function buildApiUrl(path: string) {
  const configuredBase = OpenAPI.BASE || window.location.origin
  const baseUrl = new URL(configuredBase, window.location.origin)
  const normalizedBasePath =
    baseUrl.pathname === "/" ? "" : baseUrl.pathname.replace(/\/$/, "")

  return `${baseUrl.origin}${normalizedBasePath}${path}`
}

export function getWorkshopPreviewImageUrl(
  workshopId: number | string | null | undefined,
) {
  const normalizedWorkshopId = String(workshopId ?? "").trim()
  if (!normalizedWorkshopId || !/^\d+$/.test(normalizedWorkshopId)) {
    return null
  }

  return buildApiUrl(
    `/v1/maps/workshop/${encodeURIComponent(normalizedWorkshopId)}/preview-image`,
  )
}

export function getMapPreviewImageUrl(mapName: string | null | undefined) {
  const normalizedMapName = String(mapName ?? "").trim()
  if (!normalizedMapName) {
    return null
  }

  return buildApiUrl(
    `/v1/maps/preview-image?map_name=${encodeURIComponent(normalizedMapName)}`,
  )
}

export function getLegacyMapImageUrls(
  mapName: string | null | undefined,
  workshopId?: number | string | null,
) {
  const workshopPreviewUrl =
    getWorkshopPreviewImageUrl(workshopId) ?? getMapPreviewImageUrl(mapName)

  return [getMapImageUrl(mapName), workshopPreviewUrl].filter(
    (url): url is string => Boolean(url),
  )
}
