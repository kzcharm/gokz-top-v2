import { apiUrl, testAuthHelpersEnabled } from "../config"
import { randomSteamid64 } from "./random"

export const issueSessionToken = async ({
  request,
  steamid64 = randomSteamid64(),
  roles = [],
  name = "Test User",
}: {
  request: any
  steamid64?: string | number
  roles?: string[]
  name?: string
}) => {
  if (!testAuthHelpersEnabled) {
    throw new Error(
      "ENABLE_TEST_AUTH_HELPERS=true is required for auth-backed Playwright helpers.",
    )
  }
  const response = await request.post(`${apiUrl}/v1/private/auth/session`, {
    data: {
      steamid64,
      roles,
      is_active: true,
      name,
    },
  })
  const payload = await response.json()
  return {
    steamid64,
    accessToken: payload.access_token as string,
  }
}
