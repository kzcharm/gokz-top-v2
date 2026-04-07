import { expect, test } from "@playwright/test"
import { issueSessionToken } from "./utils/privateApi"
import { randomSteamid64 } from "./utils/random"
import { logInUser, logOutUser } from "./utils/user"

test.use({ storageState: { cookies: [], origins: [] } })

test("Navigating to /login redirects to backend steam endpoint", async ({
  page,
}) => {
  await page.goto("/login")
  await expect(page).toHaveURL(/steamcommunity\.com\/openid\/loginform/)
})

test("Successful log out", async ({ page }) => {
  await logInUser(page, randomSteamid64())
  await logOutUser(page)
  await expect(page).toHaveURL(/steamcommunity\.com\/openid\/loginform/)
})

test("Logged-out user cannot access protected routes", async ({ page }) => {
  await page.goto("/settings")
  await expect(page).toHaveURL(/steamcommunity\.com\/openid\/loginform/)
})

test("Auth callback stores token from hash and redirects", async ({
  page,
  request,
}) => {
  const steamid64 = randomSteamid64()
  const { accessToken } = await issueSessionToken({
    request,
    steamid64,
  })

  await page.goto(`/auth/callback#access_token=${accessToken}`)
  await expect(page).toHaveURL(/\/servers$/)
  const tokenFromStorage = await page.evaluate(() =>
    localStorage.getItem("access_token"),
  )
  await expect(tokenFromStorage).toBe(accessToken)
})

test("Redirects to /login when token is wrong", async ({ page }) => {
  await page.goto("/settings")
  await page.evaluate(() => {
    localStorage.setItem("access_token", "invalid_token")
  })
  await page.goto("/settings")
  await expect(page).toHaveURL(/steamcommunity\.com\/openid\/loginform/)
})
