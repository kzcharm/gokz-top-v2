import { expect, test } from "@playwright/test"
import { superUserSteamid64 } from "./config"
import { randomSteamid64 } from "./utils/random"
import { logInUser, logOutUser } from "./utils/user"

const tabs = ["My profile", "Danger zone"]

test("My profile tab is active by default", async ({ page }) => {
  await page.goto("/settings")
  await expect(page.getByRole("tab", { name: "My profile" })).toHaveAttribute(
    "aria-selected",
    "true",
  )
})

test("Only steam-era tabs are visible", async ({ page }) => {
  await page.goto("/settings")
  for (const tab of tabs) {
    await expect(page.getByRole("tab", { name: tab })).toBeVisible()
  }
  await expect(page.getByRole("tab", { name: "Password" })).toHaveCount(0)
})

test.describe("Profile and theme", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Profile displays steam id", async ({ page }) => {
    const steamid64 = randomSteamid64()
    await logInUser(page, steamid64)
    await page.goto("/settings")
    await expect(page.getByText(String(steamid64))).toBeVisible()
  })

  test("Selected mode is preserved across sessions", async ({ page }) => {
    await logInUser(page, superUserSteamid64, { isSuperuser: true })
    await page.goto("/settings")

    await page.getByTestId("theme-button").click({ button: "right" })
    await page.getByTestId("dark-mode").click()
    await expect(page.locator("html")).toHaveClass(/dark/)

    await logOutUser(page)
    await logInUser(page, superUserSteamid64, { isSuperuser: true })
    await expect(page.locator("html")).toHaveClass(/dark/)
  })
})
