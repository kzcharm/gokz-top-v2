import { requestGraphQL } from "@/lib/graphql"

export type GraphqlMapImage = {
  mapName: string
  workshopId: string | null
  previewUrl: string | null
}

type MapImageRequest = {
  mapName: string
  workshopId: string | null
}

type MapImagesQueryResponse = {
  mapImages: GraphqlMapImage[]
}

type PendingMapImageBatchEntry = {
  reject: (reason?: unknown) => void
  resolve: (image: GraphqlMapImage) => void
}

type CachedMapImage = {
  image: GraphqlMapImage
  storedAt: number
}

const MAP_IMAGE_BATCH_DELAY_MS = 10
const MAP_IMAGE_CACHE_STALE_TIME_MS = 24 * 60 * 60 * 1000
const MAP_IMAGE_MISS_CACHE_STALE_TIME_MS = 60 * 60 * 1000

let pendingMapImageBatch = new Map<string, PendingMapImageBatchEntry[]>()
let pendingMapImageRequests = new Map<string, MapImageRequest>()
let pendingMapImageBatchTimer: ReturnType<typeof setTimeout> | null = null
const cachedMapImages = new Map<string, CachedMapImage>()
const inflightMapImages = new Map<string, Promise<GraphqlMapImage>>()

function normalizeMapImageRequest(
  mapName: string,
  workshopId?: number | string | null,
): MapImageRequest {
  const normalizedWorkshopId = String(workshopId ?? "").trim()
  return {
    mapName: mapName.trim(),
    workshopId: /^\d+$/.test(normalizedWorkshopId)
      ? normalizedWorkshopId
      : null,
  }
}

function getMapImageCacheKey(request: MapImageRequest) {
  return `${request.mapName}:${request.workshopId ?? "MAP"}`
}

function isCachedMapImageFresh(cached: CachedMapImage, now: number) {
  const staleTime = cached.image.previewUrl
    ? MAP_IMAGE_CACHE_STALE_TIME_MS
    : MAP_IMAGE_MISS_CACHE_STALE_TIME_MS
  return now - cached.storedAt < staleTime
}

async function requestMapImages(inputs: MapImageRequest[]) {
  if (inputs.length === 0) {
    return []
  }

  const response = await requestGraphQL<MapImagesQueryResponse>(
    `
      query MapImages($inputs: [MapImageInput!]!) {
        mapImages(inputs: $inputs) {
          mapName
          workshopId
          previewUrl
        }
      }
    `,
    { inputs },
  )
  return response.mapImages
}

function queueMapImageBatchLoad(request: MapImageRequest) {
  const cacheKey = getMapImageCacheKey(request)
  const existingPromise = inflightMapImages.get(cacheKey)
  if (existingPromise) {
    return existingPromise
  }

  const promise = new Promise<GraphqlMapImage>((resolve, reject) => {
    const existingResolvers = pendingMapImageBatch.get(cacheKey) ?? []
    existingResolvers.push({ resolve, reject })
    pendingMapImageBatch.set(cacheKey, existingResolvers)
    pendingMapImageRequests.set(cacheKey, request)

    if (pendingMapImageBatchTimer !== null) {
      return
    }
    pendingMapImageBatchTimer = setTimeout(() => {
      void flushPendingMapImageBatch()
    }, MAP_IMAGE_BATCH_DELAY_MS)
  })

  inflightMapImages.set(cacheKey, promise)
  return promise
}

async function flushPendingMapImageBatch() {
  const currentBatch = pendingMapImageBatch
  const currentRequests = pendingMapImageRequests
  pendingMapImageBatch = new Map()
  pendingMapImageRequests = new Map()
  pendingMapImageBatchTimer = null
  const requests = [...currentRequests.values()]

  try {
    const images = await requestMapImages(requests)
    requests.forEach((request, index) => {
      const cacheKey = getMapImageCacheKey(request)
      const resolvers = currentBatch.get(cacheKey) ?? []
      const image = images[index] ?? {
        mapName: request.mapName,
        workshopId: request.workshopId,
        previewUrl: null,
      }
      cachedMapImages.set(cacheKey, { image, storedAt: Date.now() })
      inflightMapImages.delete(cacheKey)
      for (const entry of resolvers) {
        entry.resolve(image)
      }
    })
  } catch (error) {
    for (const cacheKey of currentBatch.keys()) {
      inflightMapImages.delete(cacheKey)
    }
    for (const resolvers of currentBatch.values()) {
      for (const entry of resolvers) {
        entry.reject(error)
      }
    }
  }
}

export async function loadMapImage(
  mapName: string,
  workshopId?: number | string | null,
) {
  const request = normalizeMapImageRequest(mapName, workshopId)
  const cacheKey = getMapImageCacheKey(request)
  const cached = cachedMapImages.get(cacheKey)
  if (cached && isCachedMapImageFresh(cached, Date.now())) {
    return cached.image
  }
  return await queueMapImageBatchLoad(request)
}
