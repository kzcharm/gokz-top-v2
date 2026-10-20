export const MAPS_LAST_VISITED_STORAGE_KEY = "gokz-maps-last-visited-at"
export const MAPS_LAST_VISITED_EVENT = "gokz-maps-last-visited"

let lastVisitedAt: number | null = null

function saveLastVisitedAt(timestamp: number) {
  lastVisitedAt = timestamp
  try {
    localStorage.setItem(
      MAPS_LAST_VISITED_STORAGE_KEY,
      new Date(timestamp).toISOString(),
    )
  } catch {
    // Retain the baseline in memory when storage is unavailable.
  }
  return timestamp
}

export function getMapsLastVisitedAt() {
  try {
    const value = localStorage.getItem(MAPS_LAST_VISITED_STORAGE_KEY)
    const timestamp = value ? Date.parse(value) : Number.NaN
    if (Number.isFinite(timestamp)) {
      lastVisitedAt = timestamp
      return timestamp
    }
  } catch {
    // Use the in-memory baseline for the rest of this browser session.
  }
  return saveLastVisitedAt(lastVisitedAt ?? Date.now())
}

export function markMapsVisited() {
  const timestamp = saveLastVisitedAt(
    Math.max(getMapsLastVisitedAt(), Date.now()),
  )
  window.dispatchEvent(new Event(MAPS_LAST_VISITED_EVENT))
  return timestamp
}
