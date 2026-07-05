import { expect, type Page, test } from "@playwright/test"
import { randomSteamid64 } from "./utils/random"

test.use({ storageState: { cookies: [], origins: [] } })

function fakeAccessToken(steamid64: string) {
  return [
    "e30",
    Buffer.from(JSON.stringify({ sub: steamid64 })).toString("base64url"),
    "signature",
  ].join(".")
}

async function stubCurrentUser(page: Page, steamid64: string) {
  await page.route("**/v1/**", async (route) => {
    const url = route.request().url()
    if (url.endsWith("/v1/users/me")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          steamid64,
          roles: [],
          player: {
            steamid64,
            display_name: "Default Page Tester",
          },
        }),
      })
      return
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({}),
    })
  })
}

test("root defaults to servers without a saved preference", async ({
  page,
}) => {
  await page.goto("/")

  await expect(page).toHaveURL(/\/servers(\?|$)/)
})

test("root uses a saved public page preference", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("gokz-default-page", "/leaderboards")
  })

  await page.goto("/")

  await expect(page).toHaveURL(/\/leaderboards(\/players)?(\?|$)/)
})

test("profile preference opens the signed-in player's profile", async ({
  page,
}) => {
  const steamid64 = String(randomSteamid64())
  await stubCurrentUser(page, steamid64)
  await page.addInitScript(
    ({ token }) => {
      localStorage.setItem("access_token", token)
      localStorage.setItem("gokz-default-page", "/profile")
    },
    { token: fakeAccessToken(steamid64) },
  )
  await page.goto("/")

  await expect(page).toHaveURL(new RegExp(`/profile/${steamid64}$`))
})

test("profile preference falls back to servers for guests", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("gokz-default-page", "/profile")
  })

  await page.goto("/")

  await expect(page).toHaveURL(/\/servers(\?|$)/)
})

test("appearance settings saves the default page preference", async ({
  page,
}) => {
  const steamid64 = String(randomSteamid64())
  await stubCurrentUser(page, steamid64)
  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, fakeAccessToken(steamid64))
  await page.goto("/settings/appearance")

  await page.getByTestId("appearance-default-page-select").click()
  await page.getByTestId("appearance-default-page-option-live").click()

  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("gokz-default-page")))
    .toBe("/live")
})
