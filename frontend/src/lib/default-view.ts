export function readDefaultView<T>(
  storageKey: string,
  parseSettings: (value: unknown) => T | null,
): T | null {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem(storageKey) ?? "null",
    )
    if (!value || typeof value !== "object") return null
    const stored = value as Record<string, unknown>
    return stored.version === 1 ? parseSettings(stored.settings) : null
  } catch {
    return null
  }
}
