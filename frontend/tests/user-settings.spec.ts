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
