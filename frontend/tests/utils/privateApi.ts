import { apiUrl } from "../config"
import { randomSteamid64 } from "./random"

export const issueSessionToken = async ({
  request,
  steamid64 = randomSteamid64(),
  isSuperuser = false,
  name = "Test User",
}: {
  request: any
  steamid64?: number
  isSuperuser?: boolean
  name?: string
}) => {
  const response = await request.post(`${apiUrl}/api/v1/private/auth/session`, {
    data: {
      steamid64,
      is_superuser: isSuperuser,
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
