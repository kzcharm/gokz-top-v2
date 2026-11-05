import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"
import { RUN_TIME_FONT_FAMILIES, type RunTimeFont } from "@/lib/run-time"

const STORAGE_KEY = "gokz-show-hidden-maps"
const MILLISECONDS_STORAGE_KEY = "gokz-show-run-milliseconds"
const RUN_TIME_FONT_STORAGE_KEY = "gokz-run-time-font"
const GlobalPreferencesContext = createContext<{
  showHiddenMaps: boolean
  setShowHiddenMaps: (show: boolean) => void
  showMilliseconds: boolean
  setShowMilliseconds: (show: boolean) => void
  runTimeFont: RunTimeFont
  setRunTimeFont: (font: RunTimeFont) => void
} | null>(null)

export function GlobalPreferencesProvider({
  children,
}: {
  children: ReactNode
}) {
  const [showHiddenMaps, setShowHiddenMapsState] = useState(
    () => localStorage.getItem(STORAGE_KEY) === "true",
  )
  const [runTimeFont, setRunTimeFontState] = useState<RunTimeFont>(() => {
    const saved = localStorage.getItem(RUN_TIME_FONT_STORAGE_KEY)
    return saved && Object.keys(RUN_TIME_FONT_FAMILIES).includes(saved)
      ? (saved as RunTimeFont)
      : "inter"
  })
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--font-run-time",
      RUN_TIME_FONT_FAMILIES[runTimeFont],
    )
  }, [runTimeFont])
  const [showMilliseconds, setShowMillisecondsState] = useState(() => {
    const saved = localStorage.getItem(MILLISECONDS_STORAGE_KEY)
    if (saved !== null) return saved !== "false"
    return !document.cookie
      .split("; ")
      .includes("profile_runs_show_milliseconds=false")
  })
  const value = useMemo(
    () => ({
      showHiddenMaps,
      runTimeFont,
      setRunTimeFont: (font: RunTimeFont) => {
        localStorage.setItem(RUN_TIME_FONT_STORAGE_KEY, font)
        setRunTimeFontState(font)
      },
      showMilliseconds,
      setShowMilliseconds: (show: boolean) => {
        localStorage.setItem(MILLISECONDS_STORAGE_KEY, String(show))
        setShowMillisecondsState(show)
      },
      setShowHiddenMaps: (show: boolean) => {
        localStorage.setItem(STORAGE_KEY, String(show))
        setShowHiddenMapsState(show)
      },
    }),
    [showHiddenMaps, showMilliseconds, runTimeFont],
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
