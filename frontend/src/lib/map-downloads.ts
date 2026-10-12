import type { MapPublic } from "@/client"

export function getMapPackageDownloadUrl(
  maps: Pick<MapPublic, "download_url">[],
) {
  const downloadUrls = [
    ...maps.map((map) => map.download_url),
    getConfiguredLocalMapDownloadUrl(),
  ]
  for (const downloadUrl of downloadUrls) {
    if (downloadUrl?.includes("/maps/")) {
      return `${downloadUrl.split("/maps/", 1)[0]}/packages/GlobalMaps.7z`
    }
  }
  return null
}

function getConfiguredLocalMapDownloadUrl() {
  const configuredUrl = import.meta.env.VITE_LOCAL_MAP_DOWNLOAD_URL?.trim()
  if (!import.meta.env.DEV || !configuredUrl) {
    return null
  }

  return configuredUrl
}

function getLocalMapDownloadBaseUrl(downloadUrl: string) {
  try {
    const url = new URL(downloadUrl)
    const filename = url.pathname.split("/").pop() ?? ""
    if (filename.toLowerCase().endsWith(".bsp")) {
      url.pathname = url.pathname.slice(0, -filename.length)
    }
    url.pathname = url.pathname.replace(/\/?$/, "/")
    url.search = ""
    url.hash = ""
    return url
  } catch {
    return null
  }
}

export function getMapDownloadUrl(
  map: Pick<MapPublic, "download_url" | "name">,
) {
  return getMapDownloadUrlForMapName(map.name, map.download_url)
}

export function getMapDownloadUrlForMapName(
  mapName: string,
  downloadUrl?: string | null,
) {
  const localDownloadUrl = getConfiguredLocalMapDownloadUrl()
  if (localDownloadUrl) {
    const localBaseUrl = getLocalMapDownloadBaseUrl(localDownloadUrl)
    if (localBaseUrl) {
      return new URL(`${encodeURIComponent(mapName)}.bsp`, localBaseUrl).href
    }
  }

  return downloadUrl ?? null
}
