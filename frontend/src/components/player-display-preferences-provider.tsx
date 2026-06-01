import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react"

export type PlayerDisplayRatingIconScope = "primary" | "global"

export type PlayerDisplayPreferences = {
  showCountryFlag: boolean
  showRatingIcon: boolean
  ratingIconScope: PlayerDisplayRatingIconScope
}

type PlayerDisplayPreferencesProviderProps = {
  children: React.ReactNode
  defaultPreferences?: PlayerDisplayPreferences
  storageKey?: string
}

type PlayerDisplayPreferencesProviderState = PlayerDisplayPreferences & {
  setShowCountryFlag: (showCountryFlag: boolean) => void
  setShowRatingIcon: (showRatingIcon: boolean) => void
  setRatingIconScope: (ratingIconScope: PlayerDisplayRatingIconScope) => void
}

export const PLAYER_DISPLAY_PREFERENCES_STORAGE_KEY =
  "gokz-player-display-appearance"

export const DEFAULT_PLAYER_DISPLAY_PREFERENCES: PlayerDisplayPreferences = {
  showCountryFlag: true,
  showRatingIcon: true,
  ratingIconScope: "primary",
}

const initialState: PlayerDisplayPreferencesProviderState = {
  ...DEFAULT_PLAYER_DISPLAY_PREFERENCES,
  setShowCountryFlag: () => null,
  setShowRatingIcon: () => null,
  setRatingIconScope: () => null,
}

const PlayerDisplayPreferencesContext =
  createContext<PlayerDisplayPreferencesProviderState>(initialState)

function isRatingIconScope(
  value: unknown,
): value is PlayerDisplayRatingIconScope {
  return value === "primary" || value === "global"
}

function readStoredPreferences(
  storageKey: string,
  defaultPreferences: PlayerDisplayPreferences,
): PlayerDisplayPreferences {
  const storedValue = localStorage.getItem(storageKey)
  if (!storedValue) {
    return defaultPreferences
  }

  try {
    const parsedValue = JSON.parse(storedValue) as Partial<
      Record<keyof PlayerDisplayPreferences, unknown>
    >

    return {
      showCountryFlag:
        typeof parsedValue.showCountryFlag === "boolean"
          ? parsedValue.showCountryFlag
          : defaultPreferences.showCountryFlag,
      showRatingIcon:
        typeof parsedValue.showRatingIcon === "boolean"
          ? parsedValue.showRatingIcon
          : defaultPreferences.showRatingIcon,
      ratingIconScope: isRatingIconScope(parsedValue.ratingIconScope)
        ? parsedValue.ratingIconScope
        : defaultPreferences.ratingIconScope,
    }
  } catch {
    return defaultPreferences
  }
}

export function PlayerDisplayPreferencesProvider({
  children,
  defaultPreferences = DEFAULT_PLAYER_DISPLAY_PREFERENCES,
  storageKey = PLAYER_DISPLAY_PREFERENCES_STORAGE_KEY,
}: PlayerDisplayPreferencesProviderProps) {
  const [preferences, setPreferences] = useState<PlayerDisplayPreferences>(() =>
    readStoredPreferences(storageKey, defaultPreferences),
  )

  const updatePreferences = useCallback(
    (nextPreferences: PlayerDisplayPreferences) => {
      localStorage.setItem(storageKey, JSON.stringify(nextPreferences))
      setPreferences(nextPreferences)
    },
    [storageKey],
  )

  const setShowCountryFlag = useCallback(
    (showCountryFlag: boolean) => {
      updatePreferences({ ...preferences, showCountryFlag })
    },
    [preferences, updatePreferences],
  )

  const setShowRatingIcon = useCallback(
    (showRatingIcon: boolean) => {
      updatePreferences({ ...preferences, showRatingIcon })
    },
    [preferences, updatePreferences],
  )

  const setRatingIconScope = useCallback(
    (ratingIconScope: PlayerDisplayRatingIconScope) => {
      updatePreferences({ ...preferences, ratingIconScope })
    },
    [preferences, updatePreferences],
  )

  const value = useMemo(
    () => ({
      ...preferences,
      setShowCountryFlag,
      setShowRatingIcon,
      setRatingIconScope,
    }),
    [preferences, setRatingIconScope, setShowCountryFlag, setShowRatingIcon],
  )

  return (
    <PlayerDisplayPreferencesContext.Provider value={value}>
      {children}
    </PlayerDisplayPreferencesContext.Provider>
  )
}

export function usePlayerDisplayPreferences() {
  const context = useContext(PlayerDisplayPreferencesContext)

  if (context === undefined) {
    throw new Error(
      "usePlayerDisplayPreferences must be used within a PlayerDisplayPreferencesProvider",
    )
  }

  return context
}
