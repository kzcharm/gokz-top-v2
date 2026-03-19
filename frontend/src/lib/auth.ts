const DEFAULT_API_URL = "http://localhost:8000"

export function getSteamLoginUrl() {
  const apiUrl = import.meta.env.VITE_API_URL || DEFAULT_API_URL
  return `${apiUrl}/v1/login/steam`
}

export function redirectToSteamLogin({ replace = false } = {}) {
  const loginUrl = getSteamLoginUrl()

  if (replace) {
    window.location.replace(loginUrl)
    return
  }

  window.location.assign(loginUrl)
}
