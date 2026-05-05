import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"

type KeyboardPaginationSnapshot = {
  enabled: boolean
  canPrevious: boolean
  canNext: boolean
  onPrevious: () => void
  onNext: () => void
}

type KeyboardPaginationRegistration = {
  element: HTMLElement
  getSnapshot: () => KeyboardPaginationSnapshot
}

type KeyboardPaginationContextValue = {
  register: (registration: KeyboardPaginationRegistration) => () => void
}

type RegisteredPagination = KeyboardPaginationRegistration & {
  id: number
}

type ActivePagination = {
  registration: RegisteredPagination
  snapshot: KeyboardPaginationSnapshot
}

const SCROLL_STEP_RATIO = 0.8
const SCROLL_ANIMATION_DURATION_MS = 220

const EDITABLE_TARGET_SELECTOR = [
  "input",
  "textarea",
  "select",
  '[contenteditable]:not([contenteditable="false"])',
  '[role="textbox"]',
].join(", ")

const KeyboardPaginationContext =
  createContext<KeyboardPaginationContextValue | null>(null)

function isEditableEventTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) {
    return false
  }

  return target.closest(EDITABLE_TARGET_SELECTOR) !== null
}

function isVisibleElement(element: HTMLElement) {
  const rect = element.getBoundingClientRect()

  return (
    rect.width > 0 &&
    rect.height > 0 &&
    rect.bottom >= 0 &&
    rect.right >= 0 &&
    rect.top <= window.innerHeight &&
    rect.left <= window.innerWidth
  )
}

function findActivePagination(
  registrations: RegisteredPagination[],
): ActivePagination | null {
  const visibleRegistrations = registrations.filter((registration) => {
    return (
      registration.element.isConnected &&
      registration.getSnapshot().enabled &&
      isVisibleElement(registration.element)
    )
  })

  if (visibleRegistrations.length === 0) {
    return null
  }

  const activeElement = document.activeElement
  const focusedRegistration =
    activeElement instanceof Element
      ? visibleRegistrations.find((registration) =>
          registration.element.contains(activeElement),
        )
      : undefined

  const hoveredRegistration =
    focusedRegistration ??
    visibleRegistrations.find((registration) =>
      registration.element.matches(":hover"),
    )

  const registration =
    hoveredRegistration ??
    [...visibleRegistrations].sort((left, right) => {
      const position = left.element.compareDocumentPosition(right.element)

      if (position & Node.DOCUMENT_POSITION_PRECEDING) {
        return 1
      }
      if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
        return -1
      }

      return left.id - right.id
    })[0]

  if (!registration) {
    return null
  }

  return {
    registration,
    snapshot: registration.getSnapshot(),
  }
}

export function WASDNavigationProvider({ children }: { children: ReactNode }) {
  const registrationsRef = useRef<RegisteredPagination[]>([])
  const nextIdRef = useRef(1)

  const register = useCallback(
    (registration: KeyboardPaginationRegistration) => {
      const registeredPagination = {
        ...registration,
        id: nextIdRef.current,
      }
      nextIdRef.current += 1
      registrationsRef.current = [
        ...registrationsRef.current,
        registeredPagination,
      ]

      return () => {
        registrationsRef.current = registrationsRef.current.filter(
          (currentRegistration) =>
            currentRegistration.id !== registeredPagination.id,
        )
      }
    },
    [],
  )

  useEffect(() => {
    let scrollAnimationFrame: number | null = null
    let scrollAnimationStartTime: number | null = null
    let scrollAnimationStartY = 0
    let scrollAnimationTargetY = 0

    const stopScrollAnimation = () => {
      if (scrollAnimationFrame !== null) {
        window.cancelAnimationFrame(scrollAnimationFrame)
      }

      scrollAnimationFrame = null
      scrollAnimationStartTime = null
      scrollAnimationStartY = 0
      scrollAnimationTargetY = 0
    }

    const easeOutCubic = (progress: number) => {
      return 1 - (1 - progress) ** 3
    }

    const animateScroll = (timestamp: number) => {
      if (scrollAnimationStartTime === null) {
        scrollAnimationStartTime = timestamp
      }

      const elapsed = timestamp - scrollAnimationStartTime
      const progress = Math.min(elapsed / SCROLL_ANIMATION_DURATION_MS, 1)
      const easedProgress = easeOutCubic(progress)
      const nextScrollTop =
        scrollAnimationStartY +
        (scrollAnimationTargetY - scrollAnimationStartY) * easedProgress

      window.scrollTo({
        top: nextScrollTop,
      })

      if (progress < 1) {
        scrollAnimationFrame = window.requestAnimationFrame(animateScroll)
        return
      }

      stopScrollAnimation()
    }

    const scrollWithAnimation = (deltaY: number) => {
      const maxScrollTop = Math.max(
        0,
        document.documentElement.scrollHeight - window.innerHeight,
      )
      const baseScrollTop =
        scrollAnimationFrame === null ? window.scrollY : scrollAnimationTargetY
      const nextTargetY = Math.min(
        Math.max(baseScrollTop + deltaY, 0),
        maxScrollTop,
      )

      if (nextTargetY === baseScrollTop) {
        return
      }

      if (scrollAnimationFrame !== null) {
        window.cancelAnimationFrame(scrollAnimationFrame)
      }

      scrollAnimationStartY = window.scrollY
      scrollAnimationTargetY = nextTargetY
      scrollAnimationStartTime = null
      scrollAnimationFrame = window.requestAnimationFrame(animateScroll)
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        event.defaultPrevented ||
        event.isComposing ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        isEditableEventTarget(event.target)
      ) {
        return
      }

      const key = event.key.toLowerCase()

      if (key === "w" || key === "s") {
        event.preventDefault()
        scrollWithAnimation(
          window.innerHeight * SCROLL_STEP_RATIO * (key === "w" ? -1 : 1),
        )
        return
      }

      if ((key !== "a" && key !== "d") || event.repeat) {
        return
      }

      const activePagination = findActivePagination(registrationsRef.current)
      if (!activePagination) {
        return
      }

      if (key === "a" && activePagination.snapshot.canPrevious) {
        event.preventDefault()
        activePagination.snapshot.onPrevious()
        return
      }

      if (key === "d" && activePagination.snapshot.canNext) {
        event.preventDefault()
        activePagination.snapshot.onNext()
      }
    }

    window.addEventListener("keydown", handleKeyDown)

    return () => {
      stopScrollAnimation()
      window.removeEventListener("keydown", handleKeyDown)
    }
  }, [])

  const value = useMemo<KeyboardPaginationContextValue>(
    () => ({
      register,
    }),
    [register],
  )

  return (
    <KeyboardPaginationContext.Provider value={value}>
      {children}
    </KeyboardPaginationContext.Provider>
  )
}

export function useKeyboardPagination({
  enabled,
  canPrevious,
  canNext,
  onPrevious,
  onNext,
}: KeyboardPaginationSnapshot) {
  const context = useContext(KeyboardPaginationContext)
  const optionsRef = useRef<KeyboardPaginationSnapshot>({
    enabled,
    canPrevious,
    canNext,
    onPrevious,
    onNext,
  })
  const [element, setElement] = useState<HTMLElement | null>(null)

  useEffect(() => {
    optionsRef.current = {
      enabled,
      canPrevious,
      canNext,
      onPrevious,
      onNext,
    }
  }, [enabled, canPrevious, canNext, onPrevious, onNext])

  useEffect(() => {
    if (!context || !element) {
      return
    }

    return context.register({
      element,
      getSnapshot: () => optionsRef.current,
    })
  }, [context, element])

  return setElement
}
