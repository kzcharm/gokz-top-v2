import { useLayoutEffect, useRef } from "react"

/** Fit a single line to its available width without shrinking below a readable size. */
export function useFitText<T extends HTMLElement>(
  text: string,
  minFontSize: number,
  maxFontSize: number,
) {
  const ref = useRef<T>(null)

  useLayoutEffect(() => {
    const element = ref.current
    if (!element || !text) return

    const fit = () => {
      let low = minFontSize
      let high = maxFontSize
      element.style.fontSize = `${high}px`
      if (element.scrollWidth <= element.clientWidth) return

      // Measure the rendered font, including Unicode glyphs and letter spacing.
      while (high - low > 0.25) {
        const size = (low + high) / 2
        element.style.fontSize = `${size}px`
        if (element.scrollWidth > element.clientWidth) high = size
        else low = size
      }
      element.style.fontSize = `${low}px`
    }

    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(element)
    // Web fonts can finish loading after the first measurement.
    document.fonts.addEventListener("loadingdone", fit)
    return () => {
      observer.disconnect()
      document.fonts.removeEventListener("loadingdone", fit)
    }
  }, [text, minFontSize, maxFontSize])

  return ref
}
