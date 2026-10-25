import { type RefObject, useEffect, useState } from "react"

export function useTableContainerWidth(
  ref: RefObject<HTMLDivElement | null>,
  enabled: boolean,
) {
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!enabled || !ref.current) return
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(entry.contentRect.width)
    })
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [enabled, ref])
  return width
}
