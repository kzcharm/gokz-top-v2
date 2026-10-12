import { expect, type Page, test } from "@playwright/test"

const steamid64 = "76561198000000001"
const discordLink = {
  id: "019e0000-0000-7000-8000-000000000901",
  player_steamid64: steamid64,
  platform: "discord",
  account_identifier: "123456789012345678",
  url: "https://discord.com/users/123456789012345678",
  verified: true,
  show_on_site: true,
  created_at: "2026-10-12T00:00:00Z",
  updated_at: "2026-10-12T00:00:00Z",
}

test.use({ storageState: { cookies: [], origins: [] } })

async function mockSettings(page: Page, initiallyLinked = false) {
  let linked = initiallyLinked
  await page.addInitScript(() =>
    localStorage.setItem("access_token", "test-token"),
  )
  await page
    .context()
    .route("https://discord.com/oauth2/authorize**", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: "<h1>Discord authorization</h1>",
      }),
    )
  await page.context().route("**/v1/**", async (route) => {
    const url = new URL(route.request().url())
    let body: unknown = { data: [], count: 0 }
    if (url.pathname === "/v1/users/me") {
      body = {
        steamid64,
        roles: [],
        is_active: true,
        player: {
          steamid64,
          name: "Discord Player",
          display_name: "Discord Player",
        },
      }
    } else if (url.pathname.endsWith("/discord/connection-requests")) {
      body = {
        authorization_url: "https://discord.com/oauth2/authorize?test=1",
      }
    } else if (url.pathname.includes("/player-social-links/")) {
      if (route.request().method() === "DELETE") linked = false
      body = { data: linked ? [discordLink] : [], count: linked ? 1 : 0 }
    } else if (url.pathname === "/v1/graphql") {
      body = { data: { players: [] } }
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(body),
    })
  })
  return {
    link: () => {
      linked = true
    },
  }
}

async function openAdd(page: Page) {
  await page.getByRole("button", { name: "Add", exact: true }).click()
}

test("Discord popup completes linking and ignores unrelated messages", async ({
  page,
}) => {
  const state = await mockSettings(page)
  await page.goto("/settings/social-links")
  await openAdd(page)
  const popupPromise = page.waitForEvent("popup")
  await page.getByRole("button", { name: "Discord", exact: true }).click()
  const popup = await popupPromise
  await expect(popup).toHaveURL(/discord.com\/oauth2\/authorize/)
  await page.evaluate(() =>
    window.postMessage(
      { type: "discord-social-link-verification", status: "success" },
      window.location.origin,
    ),
  )
  await expect(
    page.getByText("Discord account linked", { exact: true }),
  ).toHaveCount(0)
  state.link()
  await popup.evaluate(() => {
    window.location.href =
      "http://localhost:5173/settings/social-links?discordVerification=success"
  })
  await expect(
    page.getByText("Discord account linked", { exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("link", { name: /Discord.*123456789012345678/ }),
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Edit Discord link" }),
  ).toHaveCount(0)
  await expect(
    page.getByRole("switch", { name: "Show streams/videos on GOKZ.TOP" }),
  ).toHaveCount(0)
  await page.screenshot({
    path: "../.temp/screenshots/discord-social-links-desktop.png",
    fullPage: true,
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({
    path: "../.temp/screenshots/discord-social-links-mobile.png",
    fullPage: true,
  })
  await openAdd(page)
  await expect(
    page.getByRole("button", { name: "Discord", exact: true }),
  ).toBeDisabled()
  await page.keyboard.press("Escape")
  await page.getByRole("button", { name: "Delete Discord link" }).click()
  await expect(
    page.getByRole("button", { name: "Delete Discord link" }),
  ).toHaveCount(0)
  await openAdd(page)
  await expect(
    page.getByRole("button", { name: "Discord", exact: true }),
  ).toBeEnabled()
})

test("Discord linking reports blocked popups", async ({ page }) => {
  await mockSettings(page)
  await page.addInitScript(() => {
    window.open = () => null
  })
  await page.goto("/settings/social-links")
  await openAdd(page)
  await page.getByRole("button", { name: "Discord", exact: true }).click()
  await expect(
    page.getByText("Allow popups to continue Discord linking", { exact: true }),
  ).toBeVisible()
})

test("Discord full-page return shows success and removes callback parameters", async ({
  page,
}) => {
  await mockSettings(page, true)
  await page.goto("/settings/social-links?discordVerification=success")
  await expect(
    page.getByText("Discord account linked", { exact: true }),
  ).toBeVisible()
  await expect(page).toHaveURL("http://localhost:5173/settings/social-links")
})

test("Discord callback errors keep the account unlinked", async ({ page }) => {
  await mockSettings(page)
  await page.goto(
    "/settings/social-links?discordVerification=error&message=Discord%20authorization%20was%20declined",
  )
  await expect(
    page.getByText("Discord authorization was declined", { exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Delete Discord link" }),
  ).toHaveCount(0)
})
