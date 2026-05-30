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

type AdminModeContextValue = {
  enabled: boolean
  available: boolean
  registerSurface: (id: symbol, active: boolean) => void
  setEnabled: (enabled: boolean) => void
  toggle: () => void
}

const AdminModeContext = createContext<AdminModeContextValue | null>(null)

export function AdminModeProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState(false)
  const [activeSurfaceIds, setActiveSurfaceIds] = useState<Set<symbol>>(
    () => new Set(),
  )
  const available = activeSurfaceIds.size > 0

  useEffect(() => {
    const reset = () => setEnabled(false)
    window.addEventListener("pagehide", reset)
    window.addEventListener("beforeunload", reset)
    return () => {
      window.removeEventListener("pagehide", reset)
      window.removeEventListener("beforeunload", reset)
    }
  }, [])

  useEffect(() => {
    if (!available) {
      setEnabled(false)
    }
  }, [available])

  const registerSurface = useCallback((id: symbol, active: boolean) => {
    setActiveSurfaceIds((currentIds) => {
      const alreadyActive = currentIds.has(id)
      if (active === alreadyActive) {
        return currentIds
      }

      const nextIds = new Set(currentIds)
      if (active) {
        nextIds.add(id)
      } else {
        nextIds.delete(id)
      }
      return nextIds
    })
  }, [])

  const value = useMemo<AdminModeContextValue>(
    () => ({
      enabled,
      available,
      registerSurface,
      setEnabled,
      toggle: () => setEnabled((current) => !current),
    }),
    [available, enabled, registerSurface],
  )

  return (
    <AdminModeContext.Provider value={value}>
      {children}
    </AdminModeContext.Provider>
  )
}

export function useAdminMode() {
  const context = useContext(AdminModeContext)
  if (context === null) {
    throw new Error("useAdminMode must be used within an AdminModeProvider.")
  }
  return context
}

export function useAdminModeSurface(active: boolean) {
  const { registerSurface } = useAdminMode()
  const surfaceIdRef = useRef<symbol>(Symbol("admin-mode-surface"))

  useEffect(() => {
    const surfaceId = surfaceIdRef.current
    registerSurface(surfaceId, active)
    return () => registerSurface(surfaceId, false)
  }, [active, registerSurface])
}
