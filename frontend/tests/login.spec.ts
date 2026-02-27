import { expect, test } from "@playwright/test"
import { logInUser, logOutUser } from "./utils/user"
import { randomSteamid64 } from "./utils/random"
import { issueSessionToken } from "./utils/privateApi"

test.use({ storageState: { cookies: [], origins: [] } })

test("Steam login button is visible", async ({ page }) => {
  await page.goto("/login")
  await expect(page.getByTestId("sidebar-login-button")).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Continue with Steam" }),
  ).toBeVisible()
})

test("Login button redirects to backend steam endpoint", async ({ page }) => {
  await page.goto("/login")
  await page.getByRole("button", { name: "Continue with Steam" }).click()
  await expect(page).toHaveURL(/\/api\/v1\/login\/steam/)
})

test("Login page stays accessible even with existing token", async ({
  page,
  request,
}) => {
  const { accessToken } = await issueSessionToken({
    request,
    steamid64: randomSteamid64(),
  })
  await page.goto("/login")
  await page.evaluate((token) => {
    localStorage.setItem("access_token", token)
  }, accessToken)
  await page.goto("/login")
  await expect(page).toHaveURL("/login")
  await expect(page.getByTestId("sidebar-login-button")).toBeVisible()
})

test("Successful log out", async ({ page }) => {
  await logInUser(page, randomSteamid64())
  await logOutUser(page)
  await expect(page).toHaveURL("/login")
})

test("Logged-out user cannot access protected routes", async ({ page }) => {
  await page.goto("/settings")
  await expect(page).toHaveURL("/login")
})

test("Auth callback stores token from hash and redirects", async ({
  page,
  request,
}) => {
  const { accessToken } = await issueSessionToken({
    request,
    steamid64: randomSteamid64(),
  })

  await page.goto(`/auth/callback#access_token=${accessToken}`)
  await expect(page).toHaveURL("/")
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
  await expect(page).toHaveURL("/login")
})
