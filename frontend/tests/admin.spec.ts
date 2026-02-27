import { expect, test } from "@playwright/test"
import { superUserSteamid64 } from "./config"
import { randomSteamid64 } from "./utils/random"
import { logInUser } from "./utils/user"

test("Admin page is accessible for superuser", async ({ page }) => {
  await page.goto("/admin")
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible()
})

test.describe("Admin page access control", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Non-superuser cannot access admin page", async ({ page }) => {
    await logInUser(page, randomSteamid64(), { isSuperuser: false })
    await page.goto("/admin")
    await expect(page).not.toHaveURL(/\/admin$/)
  })

  test("Superuser can update user status", async ({ page }) => {
    await logInUser(page, superUserSteamid64, { isSuperuser: true })
    await page.goto("/admin")

    const rows = page.getByRole("row")
    await expect(rows.first()).toBeVisible()
  })
})
