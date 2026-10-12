import { expect, test } from "@playwright/test"

// Exercise browser redirects without a Steam account or a backend session helper.
const steamid64 = "76561198000000001"
const accessToken = `header.${Buffer.from(JSON.stringify({ sub: steamid64 })).toString("base64url")}.signature`
const returnToKey = "gokz-auth-return-to"

test.use({ storageState: { cookies: [], origins: [] } })

test.beforeEach(async ({ page }) => {
  await page.route("**/v1/**", async (route) => {
    if (new URL(route.request().url()).pathname === "/v1/login/steam") {
      await route.fulfill({ contentType: "text/html", body: "Steam sign-in" })
      return
    }
    await route.fulfill({ status: 503, json: { detail: "Offline test" } })
  })
})

test("sidebar login returns to /servers after Steam sign-in", async ({
  page,
}) => {
  await page.goto("/servers?region=RU#server-list")
  await page.getByTestId("sidebar-login-button").click()
  await expect(page).toHaveURL(/\/v1\/login\/steam$/)

  await page.goto(`/auth/callback#access_token=${accessToken}`)
  await expect(page).toHaveURL(/\/servers\?region=RU#server-list$/)
  expect(await page.evaluate(() => localStorage.getItem("access_token"))).toBe(
    accessToken,
  )
  expect(
    await page.evaluate((key) => sessionStorage.getItem(key), returnToKey),
  ).toBeNull()
})

test("direct /login does not save itself as the return destination", async ({
  page,
}) => {
  await page.goto("/login")
  await expect(page).toHaveURL(/\/v1\/login\/steam$/)
  await page.goto(`/auth/callback#access_token=${accessToken}`)
  await expect(page).toHaveURL(new RegExp(`/profile/${steamid64}$`))
})

for (const destination of [
  "/login",
  "/login?from=servers#sign-in",
  "/login/",
  "/auth/callback#access_token=old",
  "//example.com",
  "/\\example.com",
]) {
  test(`callback ignores unsafe return destination ${destination}`, async ({
    page,
  }) => {
    await page.addInitScript(
      ({ key, value }) => sessionStorage.setItem(key, value),
      { key: returnToKey, value: destination },
    )
    await page.goto(`/auth/callback#access_token=${accessToken}`)
    await expect(page).toHaveURL(new RegExp(`/profile/${steamid64}$`))
  })
}

test("signed-in visitors to /login stay on the website", async ({ page }) => {
  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, accessToken)
  await page.goto("/login")
  await expect(page).toHaveURL(new RegExp(`/profile/${steamid64}$`))
})
