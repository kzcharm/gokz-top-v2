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

type PaginationDirection = "previous" | "next"

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

function getVisibleViewportArea(element: HTMLElement) {
  const rect = element.getBoundingClientRect()
  const visibleWidth =
    Math.min(rect.right, window.innerWidth) - Math.max(rect.left, 0)
  const visibleHeight =
    Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0)

  if (visibleWidth <= 0 || visibleHeight <= 0) {
    return 0
  }

  return visibleWidth * visibleHeight
}

function canHandleDirection(
  snapshot: KeyboardPaginationSnapshot,
  direction: PaginationDirection,
) {
  return direction === "previous" ? snapshot.canPrevious : snapshot.canNext
}

function findActivePagination(
  registrations: RegisteredPagination[],
  direction: PaginationDirection,
): ActivePagination | null {
  const enabledRegistrations = registrations
    .filter((registration) => {
      return (
        registration.element.isConnected && registration.getSnapshot().enabled
      )
    })
    .map((registration) => ({
      registration,
      snapshot: registration.getSnapshot(),
    }))
    .filter(({ snapshot }) => canHandleDirection(snapshot, direction))

  if (enabledRegistrations.length === 0) {
    return null
  }

  const activeElement = document.activeElement
  const focusedRegistration =
    activeElement instanceof Element
      ? enabledRegistrations.find(({ registration }) =>
          registration.element.contains(activeElement),
        )
      : undefined

  if (focusedRegistration) {
    return focusedRegistration
  }

  if (enabledRegistrations.length === 1) {
    return enabledRegistrations[0]
  }

  const visibleRegistrations = enabledRegistrations.filter(({ registration }) =>
    isVisibleElement(registration.element),
  )
  const hoveredRegistration = visibleRegistrations.find(({ registration }) =>
    registration.element.matches(":hover"),
  )

  if (hoveredRegistration) {
    return hoveredRegistration
  }

  if (visibleRegistrations.length === 1) {
    return visibleRegistrations[0]
  }

  const registration = [...visibleRegistrations].sort((left, right) => {
    const visibleAreaDifference =
      getVisibleViewportArea(right.registration.element) -
      getVisibleViewportArea(left.registration.element)

    if (visibleAreaDifference !== 0) {
      return visibleAreaDifference
    }

    const position = left.registration.element.compareDocumentPosition(
      right.registration.element,
    )

    if (position & Node.DOCUMENT_POSITION_PRECEDING) {
      return 1
    }
    if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
      return -1
    }

    return left.registration.id - right.registration.id
  })[0]

  if (!registration) {
    return enabledRegistrations[enabledRegistrations.length - 1] ?? null
  }

  return registration
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

      if (key === "a") {
        const activePagination = findActivePagination(
          registrationsRef.current,
          "previous",
        )
        if (!activePagination) {
          return
        }

        event.preventDefault()
        activePagination.snapshot.onPrevious()
        return
      }

      const activePagination = findActivePagination(
        registrationsRef.current,
        "next",
      )
      if (!activePagination) {
        return
      }

      if (key === "d") {
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
