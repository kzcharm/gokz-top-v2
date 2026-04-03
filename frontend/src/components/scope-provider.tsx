import { createContext, useContext, useMemo, useState } from "react"

export type AppScope = "OVR" | "KZT" | "SKZ" | "VNL"

type ScopeProviderProps = {
  children: React.ReactNode
  defaultScope?: AppScope
  storageKey?: string
}

type ScopeProviderState = {
  scope: AppScope
  setScope: (scope: AppScope) => void
}

const VALID_SCOPES: AppScope[] = ["OVR", "KZT", "SKZ", "VNL"]

const initialState: ScopeProviderState = {
  scope: "OVR",
  setScope: () => null,
}

const ScopeProviderContext = createContext<ScopeProviderState>(initialState)

function isAppScope(value: string | null): value is AppScope {
  return value !== null && VALID_SCOPES.includes(value as AppScope)
}

export function ScopeProvider({
  children,
  defaultScope = "OVR",
  storageKey = "gokz-app-scope",
  ...props
}: ScopeProviderProps) {
  const [scope, setScope] = useState<AppScope>(() => {
    const storedScope = localStorage.getItem(storageKey)
    return isAppScope(storedScope) ? storedScope : defaultScope
  })

  const value = useMemo(
    () => ({
      scope,
      setScope: (nextScope: AppScope) => {
        localStorage.setItem(storageKey, nextScope)
        setScope(nextScope)
      },
    }),
    [scope, storageKey],
  )

  return (
    <ScopeProviderContext.Provider {...props} value={value}>
      {children}
    </ScopeProviderContext.Provider>
  )
}

export function useScope() {
  const context = useContext(ScopeProviderContext)

  if (context === undefined) {
    throw new Error("useScope must be used within a ScopeProvider")
  }

  return context
}
