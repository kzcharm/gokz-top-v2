import { test as setup } from "@playwright/test"
import { apiUrl, superUserSteamid64 } from "./config.ts"

const authFile = "playwright/.auth/user.json"

setup("authenticate", async ({ page, request }) => {
  const response = await request.post(`${apiUrl}/v1/private/auth/session`, {
    data: {
      steamid64: superUserSteamid64,
      is_superuser: true,
      is_active: true,
      name: "Super User",
    },
  })
  const payload = await response.json()

  await page.addInitScript((accessToken) => {
    localStorage.setItem("access_token", accessToken)
  }, payload.access_token)
  await page.goto("/")
  await page.context().storageState({ path: authFile })
})
