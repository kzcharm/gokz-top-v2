import { useEffect, useRef } from "react"

const SPOTLIGHT_CLASS = "leaderboard-self-spotlight"
const SCROLL_DELAY_MS = 450
const ANIMATION_DURATION_MS = 1800

/** Scroll to and animate a player once their paginated table row is rendered. */
export function usePlayerRowSpotlight({
  steamid64,
  rowReady,
  onStarted,
}: {
  steamid64: string | null
  rowReady: boolean
  onStarted: (value: null) => void
}) {
  const startTimeoutRef = useRef<number | null>(null)
  const endTimeoutRef = useRef<number | null>(null)
  const activeRowRef = useRef<HTMLTableRowElement | null>(null)

  useEffect(() => {
    return () => {
      if (startTimeoutRef.current !== null)
        window.clearTimeout(startTimeoutRef.current)
      if (endTimeoutRef.current !== null)
        window.clearTimeout(endTimeoutRef.current)
      activeRowRef.current?.classList.remove(SPOTLIGHT_CLASS)
    }
  }, [])

  useEffect(() => {
    if (!steamid64 || !rowReady) return
    const row = document.querySelector<HTMLTableRowElement>(
      `[data-player-steamid64="${CSS.escape(steamid64)}"]`,
    )
    if (!row) return

    if (startTimeoutRef.current !== null)
      window.clearTimeout(startTimeoutRef.current)
    if (endTimeoutRef.current !== null)
      window.clearTimeout(endTimeoutRef.current)
    activeRowRef.current?.classList.remove(SPOTLIGHT_CLASS)
    activeRowRef.current = row

    // Scroll the page explicitly: native scrollIntoView can scroll/clamp the
    // table's overflow containers instead of bringing the row into the viewport.
    const bounds = row.getBoundingClientRect()
    window.scrollTo({
      top:
        window.scrollY + bounds.top - (window.innerHeight - bounds.height) / 2,
      behavior: "smooth",
    })
    startTimeoutRef.current = window.setTimeout(() => {
      row.classList.remove(SPOTLIGHT_CLASS)
      void row.getBoundingClientRect()
      row.classList.add(SPOTLIGHT_CLASS)
      startTimeoutRef.current = null
      endTimeoutRef.current = window.setTimeout(() => {
        row.classList.remove(SPOTLIGHT_CLASS)
        endTimeoutRef.current = null
        activeRowRef.current = null
      }, ANIMATION_DURATION_MS)
    }, SCROLL_DELAY_MS)
    onStarted(null)
  }, [onStarted, rowReady, steamid64])
}
