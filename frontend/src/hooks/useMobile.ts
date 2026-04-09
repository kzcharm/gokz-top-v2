import * as React from "react"

export const MOBILE_BREAKPOINT = 768

export function useMediaQuery(query: string) {
  const [matches, setMatches] = React.useState<boolean | undefined>(undefined)

  React.useEffect(() => {
    const mediaQueryList = window.matchMedia(query)
    const onChange = () => {
      setMatches(mediaQueryList.matches)
    }

    onChange()
    mediaQueryList.addEventListener("change", onChange)

    return () => mediaQueryList.removeEventListener("change", onChange)
  }, [query])

  return !!matches
}

export function useIsMobile() {
  return useMediaQuery(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
}
