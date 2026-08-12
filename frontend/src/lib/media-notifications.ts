export const MEDIA_LAST_VISITED_STORAGE_KEY = "gokz-media-last-visited-at"
export const MEDIA_LAST_VISITED_EVENT = "gokz-media-last-visited"

export function getMediaLastVisitedAt() {
  try {
    const value = localStorage.getItem(MEDIA_LAST_VISITED_STORAGE_KEY)
    const timestamp = value ? Date.parse(value) : Number.NaN
    return Number.isFinite(timestamp) ? timestamp : null
  } catch {
    return null
  }
}

export function markMediaVisited() {
  const visitedAt = Date.now()
  try {
    localStorage.setItem(
      MEDIA_LAST_VISITED_STORAGE_KEY,
      new Date(visitedAt).toISOString(),
    )
  } catch {
    // Keep the dot dismissed for this visit when storage is unavailable.
  }
  window.dispatchEvent(new Event(MEDIA_LAST_VISITED_EVENT))
  return visitedAt
}
