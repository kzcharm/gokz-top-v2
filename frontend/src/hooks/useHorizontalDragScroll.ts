import { useEffect, useRef } from "react"

const DEFAULT_IGNORE_SELECTOR = [
  "a",
  "button",
  "input",
  "textarea",
  "select",
  "label",
  "summary",
  '[role="button"]',
  '[role="link"]',
  '[contenteditable="true"]',
  "[data-drag-scroll-ignore]",
].join(", ")

export function useHorizontalDragScroll<T extends HTMLElement>({
  ignoreSelector = DEFAULT_IGNORE_SELECTOR,
}: {
  ignoreSelector?: string
} = {}) {
  const containerRef = useRef<T | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    let pointerId: number | null = null
    let startX = 0
    let startY = 0
    let startScrollLeft = 0
    let isDragging = false
    let didDrag = false
    let suppressClick = false

    const resetDragState = () => {
      if (pointerId !== null && container.hasPointerCapture(pointerId)) {
        try {
          container.releasePointerCapture(pointerId)
        } catch {
          // Ignore release errors when the pointer is already gone.
        }
      }

      pointerId = null
      startX = 0
      startY = 0
      startScrollLeft = 0
      isDragging = false
      container.style.cursor = "grab"
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (event.button !== 0) {
        return
      }

      if (container.scrollWidth <= container.clientWidth) {
        return
      }

      const target = event.target instanceof Element ? event.target : null
      if (target?.closest(ignoreSelector)) {
        return
      }

      pointerId = event.pointerId
      startX = event.clientX
      startY = event.clientY
      startScrollLeft = container.scrollLeft
      isDragging = false
      didDrag = false
    }

    const handlePointerMove = (event: PointerEvent) => {
      if (pointerId !== event.pointerId) {
        return
      }

      const deltaX = event.clientX - startX
      const deltaY = event.clientY - startY

      if (!isDragging) {
        if (Math.abs(deltaX) < 8 || Math.abs(deltaX) <= Math.abs(deltaY)) {
          return
        }

        if (window.getSelection()?.type === "Range") {
          return
        }

        isDragging = true
        container.style.cursor = "grabbing"
        container.setPointerCapture(event.pointerId)
      }

      event.preventDefault()
      didDrag = true
      container.scrollLeft = startScrollLeft - deltaX
    }

    const handlePointerEnd = (event: PointerEvent) => {
      if (pointerId !== event.pointerId) {
        return
      }

      if (didDrag) {
        suppressClick = true
      }

      resetDragState()
    }

    const handleClickCapture = (event: MouseEvent) => {
      if (!suppressClick) {
        return
      }

      suppressClick = false
      event.preventDefault()
      event.stopPropagation()
    }

    container.style.cursor =
      container.scrollWidth > container.clientWidth ? "grab" : ""
    container.style.touchAction = "pan-y"

    container.addEventListener("pointerdown", handlePointerDown)
    container.addEventListener("pointermove", handlePointerMove)
    container.addEventListener("pointerup", handlePointerEnd)
    container.addEventListener("pointercancel", handlePointerEnd)
    container.addEventListener("lostpointercapture", handlePointerEnd)
    container.addEventListener("click", handleClickCapture, true)

    return () => {
      resetDragState()
      container.style.cursor = ""
      container.style.touchAction = ""
      container.removeEventListener("pointerdown", handlePointerDown)
      container.removeEventListener("pointermove", handlePointerMove)
      container.removeEventListener("pointerup", handlePointerEnd)
      container.removeEventListener("pointercancel", handlePointerEnd)
      container.removeEventListener("lostpointercapture", handlePointerEnd)
      container.removeEventListener("click", handleClickCapture, true)
    }
  }, [ignoreSelector])

  return containerRef
}
