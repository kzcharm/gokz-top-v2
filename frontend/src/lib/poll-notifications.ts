export const POLLS_LAST_VISITED_STORAGE_KEY = "gokz-polls-last-visited-at"
export const POLLS_LAST_VISITED_EVENT = "gokz-polls-last-visited"

export function getPollsLastVisitedAt() {
  try {
    const value = localStorage.getItem(POLLS_LAST_VISITED_STORAGE_KEY)
    const timestamp = value ? Date.parse(value) : Number.NaN
    return Number.isFinite(timestamp) ? timestamp : null
  } catch {
    return null
  }
}

export function markPollsVisited() {
  const visitedAt = Date.now()
  try {
    localStorage.setItem(
      POLLS_LAST_VISITED_STORAGE_KEY,
      new Date(visitedAt).toISOString(),
    )
  } catch {
    // Keep the dot dismissed for this visit when storage is unavailable.
  }
  window.dispatchEvent(new Event(POLLS_LAST_VISITED_EVENT))
  return visitedAt
}
