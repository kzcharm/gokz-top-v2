import {
  createContext,
  type ReactNode,
  useContext,
  useMemo,
  useState,
} from "react"

const STORAGE_KEY = "gokz-show-hidden-maps"
const GlobalPreferencesContext = createContext<{
  showHiddenMaps: boolean
  setShowHiddenMaps: (show: boolean) => void
} | null>(null)

export function GlobalPreferencesProvider({
  children,
}: {
  children: ReactNode
}) {
  const [showHiddenMaps, setShowHiddenMapsState] = useState(
    () => localStorage.getItem(STORAGE_KEY) === "true",
  )
  const value = useMemo(
    () => ({
      showHiddenMaps,
      setShowHiddenMaps: (show: boolean) => {
        localStorage.setItem(STORAGE_KEY, String(show))
        setShowHiddenMapsState(show)
      },
    }),
    [showHiddenMaps],
  )
  return (
    <GlobalPreferencesContext.Provider value={value}>
      {children}
    </GlobalPreferencesContext.Provider>
  )
}

export function useGlobalPreferences() {
  const context = useContext(GlobalPreferencesContext)
  if (!context)
    throw new Error("useGlobalPreferences requires GlobalPreferencesProvider")
  return context
}
