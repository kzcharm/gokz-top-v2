import { OpenAPI } from "@/client/core/OpenAPI"

export function getMapImageUrl(mapName: string | null | undefined) {
  if (!mapName || mapName.trim() === "") {
    return null
  }

  return buildApiUrl(
    `/v1/maps/images/${encodeURIComponent(mapName.trim())}.webp`,
  )
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

// Resolve one source at a time so CSS backgrounds never fetch a hidden fallback.
export async function loadFirstMapImage(
  urls: string[],
): Promise<string | null> {
  for (const url of [...new Set(urls)]) {
    const loaded = await new Promise<boolean>((resolve) => {
      const image = new Image()
      const timer = window.setTimeout(() => finish(false), 15000)
      const finish = (success: boolean) => {
        window.clearTimeout(timer)
        image.onload = null
        image.onerror = null
        resolve(success)
      }
      image.onload = () => finish(true)
      image.onerror = () => finish(false)
      image.src = url
    })
    if (loaded) return url
  }
  return null
}
