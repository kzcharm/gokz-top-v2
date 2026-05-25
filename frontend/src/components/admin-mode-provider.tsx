import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"

type AdminModeContextValue = {
  enabled: boolean
  setEnabled: (enabled: boolean) => void
  toggle: () => void
}

const AdminModeContext = createContext<AdminModeContextValue | null>(null)

export function AdminModeProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    const reset = () => setEnabled(false)
    window.addEventListener("pagehide", reset)
    window.addEventListener("beforeunload", reset)
    return () => {
      window.removeEventListener("pagehide", reset)
      window.removeEventListener("beforeunload", reset)
    }
  }, [])

  const value = useMemo<AdminModeContextValue>(
    () => ({
      enabled,
      setEnabled,
      toggle: () => setEnabled((current) => !current),
    }),
    [enabled],
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
