import {
  defaultParseSearch,
  defaultStringifySearch,
} from "@tanstack/react-router"

const playerKeys = ["player1", "player2"] as const

// SteamID64 exceeds Number.MAX_SAFE_INTEGER. Read these identifiers from the
// original query before JSON/number coercion can discard their final digits.
export function parseSearch(search: string) {
  const parsed: Record<string, unknown> = defaultParseSearch(search)
  const params = new URLSearchParams(search)
  for (const key of playerKeys) {
    const value = params.get(key)
    if (value !== null) {
      parsed[key] = /^"\d{17}"$/.test(value) ? value.slice(1, -1) : value
    }
  }
  return parsed
}

export function stringifySearch(search: Record<string, unknown>) {
  const params = new URLSearchParams(defaultStringifySearch(search))
  for (const key of playerKeys) {
    if (typeof search[key] === "string") params.set(key, search[key])
  }
  const query = params.toString()
  return query ? `?${query}` : ""
}
