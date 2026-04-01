const DEFAULT_API_URL = "http://localhost:8000"

export function getSteamLoginUrl() {
  const apiUrl = import.meta.env.VITE_API_URL || DEFAULT_API_URL
  return `${apiUrl}/v1/login/steam`
}

function decodeBase64Url(value: string) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/")
  const padded = normalized.padEnd(
    normalized.length + ((4 - (normalized.length % 4)) % 4),
    "=",
  )
  return atob(padded)
}

export function getSteamid64FromAccessToken(token: string | null) {
  if (!token) {
    return null
  }

  const [, payload] = token.split(".")
  if (!payload) {
    return null
  }

  try {
    const parsed = JSON.parse(decodeBase64Url(payload)) as { sub?: unknown }
    return typeof parsed.sub === "string" && /^\d+$/.test(parsed.sub)
      ? parsed.sub
      : null
  } catch {
    return null
  }
}

export function redirectToSteamLogin({ replace = false } = {}) {
  const loginUrl = getSteamLoginUrl()

  if (replace) {
    window.location.replace(loginUrl)
    return
  }

  window.location.assign(loginUrl)
}
