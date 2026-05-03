import { expect, test } from "@playwright/test"
import { superUserSteamid64 } from "./config"
import { randomSteamid64 } from "./utils/random"
import { logInUser } from "./utils/user"

test("My profile tab is active by default", async ({ page }) => {
  await page.goto("/settings")
  await expect(page.getByRole("tab", { name: "My profile" })).toHaveAttribute(
    "aria-selected",
    "true",
  )
  await expect(page.getByRole("tab", { name: "Danger zone" })).toHaveCount(0)
})

test("Only steam-era tabs are visible", async ({ page }) => {
  await page.goto("/settings")
  await expect(page.getByRole("tab", { name: "My profile" })).toBeVisible()
  await expect(page.getByRole("tab", { name: "Appearance" })).toBeVisible()
  await expect(page.getByRole("tab", { name: "Danger zone" })).toHaveCount(0)
  await expect(page.getByRole("tab", { name: "Password" })).toHaveCount(0)
})

test.describe("Profile and theme", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Profile displays steam id", async ({ page }) => {
    const steamid64 = randomSteamid64()
    await logInUser(page, steamid64)
    await page.goto("/settings")
    await expect(page.locator("p.font-mono.text-sm")).toHaveText(
      String(steamid64),
    )
  })

  test("Social links tab can add and delete a link", async ({ page }) => {
    const steamid64 = randomSteamid64()
    let links: unknown[] = []
    await logInUser(page, steamid64)
    await page.route(
      new RegExp(`/v1/players/${steamid64}/social-links$`),
      async (route) => {
        if (route.request().method() === "POST") {
          links = [
            {
              id: "019e0000-0000-7000-8000-000000000201",
              player_steamid64: String(steamid64),
              platform: "x",
              account_identifier: "settings_user",
              verified: false,
              url: "https://x.com/settings_user",
              created_at: "2026-04-01T00:00:00Z",
              updated_at: "2026-04-01T00:00:00Z",
            },
          ]
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )
    await page.route(
      new RegExp(`/v1/players/${steamid64}/social-links/[^/]+$`),
      async (route) => {
        if (route.request().method() === "DELETE") {
          links = []
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )

    await page.goto("/settings")
    await page.getByRole("tab", { name: "Social links" }).click()
    await page
      .getByRole("textbox", { name: "Social profile URL" })
      .fill("https://x.com/settings_user")
    await page.getByRole("button", { name: "Add" }).click()

    await expect(page.getByText("settings_user")).toBeVisible()
    await expect(page.getByText("Unverified")).toBeVisible()

    await page.getByRole("button", { name: "Delete X link" }).click()
    await expect(page.getByText("No social links added yet.")).toBeVisible()
  })

  test("Theme selected in appearance settings is preserved across sessions", async ({
    page,
  }) => {
    await logInUser(page, superUserSteamid64, { isSuperuser: true })
    await page.goto("/settings")

    await page.getByRole("tab", { name: "Appearance" }).click()
    await page.getByTestId("appearance-theme-select").click()
    await page.getByTestId("appearance-theme-option-light").click()
    await expect(page.locator("html")).toHaveClass(/light/)

    await page.evaluate(() => {
      localStorage.removeItem("access_token")
    })
    await logInUser(page, superUserSteamid64, { isSuperuser: true })
    await expect(page.locator("html")).toHaveClass(/light/)
  })

  test("Datetime settings default to iso-like, show previews, and support 12h", async ({
    page,
  }) => {
    await logInUser(page, superUserSteamid64, { isSuperuser: true })
    await page.goto("/settings")

    await page.getByRole("tab", { name: "Appearance" }).click()
    await expect(
      page.getByTestId("appearance-datetime-preset-select"),
    ).toContainText("ISO-like")
    await expect(
      page.getByTestId("appearance-datetime-preview-default"),
    ).toContainText("2026-03-22 14:05")
    await expect(
      page.getByTestId("appearance-datetime-preview-seconds"),
    ).toContainText("2026-03-22 14:05:09")

    await page.getByTestId("appearance-datetime-preset-select").click()
    await expect(
      page.getByTestId("appearance-datetime-preset-option-iso"),
    ).toContainText("2026-03-22 14:05")
    await expect(
      page.getByTestId("appearance-datetime-preset-option-us"),
    ).toContainText("03/22/2026")
    await expect(
      page.getByTestId("appearance-datetime-preset-option-euro"),
    ).toContainText("22/03/2026")
    await expect(
      page.getByTestId("appearance-datetime-preset-option-long"),
    ).toContainText("March")
    await page.getByTestId("appearance-datetime-preset-option-iso").click()

    await page.getByTestId("appearance-hour-cycle-select").click()
    await expect(
      page.getByTestId("appearance-hour-cycle-option-24h"),
    ).toContainText("2026-03-22 14:05")
    await expect(
      page.getByTestId("appearance-hour-cycle-option-12h"),
    ).toContainText("2026-03-22 02:05 PM")
    await page.getByTestId("appearance-hour-cycle-option-12h").click()

    await expect(
      page.getByTestId("appearance-hour-cycle-select"),
    ).toContainText("12-hour")
    await expect(
      page.getByTestId("appearance-datetime-preview-default"),
    ).toContainText("2026-03-22 02:05 PM")
    await expect(
      page.getByTestId("appearance-datetime-preview-seconds"),
    ).toContainText("2026-03-22 02:05:09 PM")
    await expect(
      page.getByTestId("appearance-datetime-preview-relative"),
    ).toContainText("1 hour ago")

    await page.reload()
    await page.getByRole("tab", { name: "Appearance" }).click()
    await expect(
      page.getByTestId("appearance-datetime-preset-select"),
    ).toContainText("ISO-like")
    await expect(
      page.getByTestId("appearance-hour-cycle-select"),
    ).toContainText("12-hour")

    await page.goto("/admin/players")
    await expect(page.getByRole("heading", { name: "Players" })).toBeVisible()
    await expect(
      page.getByText(/2026-\d{2}-\d{2} \d{2}:\d{2} [AP]M/).first(),
    ).toBeVisible()
    await expect(
      page.getByText(/2026-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [AP]M/),
    ).toHaveCount(0)
  })
})
