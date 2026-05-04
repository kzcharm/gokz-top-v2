import { test as setup } from "@playwright/test"
import { apiUrl, superUserSteamid64, testAuthHelpersEnabled } from "./config.ts"

const authFile = "playwright/.auth/user.json"

setup("authenticate", async ({ page, request }) => {
  if (!testAuthHelpersEnabled) {
    throw new Error(
      "Playwright test auth helpers are disabled. Set ENABLE_TEST_AUTH_HELPERS=true and point the backend at a disposable test database before running auth-backed E2E tests.",
    )
  }
  const response = await request.post(`${apiUrl}/v1/private/auth/session`, {
    data: {
      steamid64: superUserSteamid64,
      roles: ["superuser"],
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
