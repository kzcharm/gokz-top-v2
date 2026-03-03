import { expect, test } from "@playwright/test"
import { apiUrl, superUserSteamid64 } from "./config"
import { issueSessionToken } from "./utils/privateApi"
import { randomSteamid64 } from "./utils/random"
import { logInUser } from "./utils/user"

test("Admin root redirects to users page", async ({ page }) => {
  await page.goto("/admin")
  await expect(page).toHaveURL(/\/admin\/users$/)
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible()
})

test("Superuser can access users and players admin pages", async ({ page }) => {
  await page.goto("/admin/users")
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible()
  await expect(page.getByText("Website users for this project")).toBeVisible()

  await page.goto("/admin/players")
  await expect(page.getByRole("heading", { name: "Players" })).toBeVisible()
  await expect(
    page.getByText(
      "all Steam Players (who has played or potentially will play kz ( some mapper doesn't even played once, but we need to ensure them here)",
    ),
  ).toBeVisible()
})

test.describe("Admin page access control", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Non-superuser cannot access users or players admin pages", async ({
    page,
  }) => {
    await logInUser(page, randomSteamid64(), { isSuperuser: false })

    await page.goto("/admin/users")
    await expect(page).not.toHaveURL(/\/admin\/users$/)

    await page.goto("/admin/players")
    await expect(page).not.toHaveURL(/\/admin\/players$/)
  })
})

test("PlayerDisplay renders alias fallback, avatar, and country tooltip", async ({
  page,
}) => {
  const aliasName = `Alias ${Date.now()}`
  const fallbackName = `Fallback ${Date.now()}`

  const aliasPlayer = await issueSessionToken({
    request: page.request,
    steamid64: randomSteamid64(),
    isSuperuser: false,
    name: `Source ${Date.now()}`,
  })
  const fallbackPlayer = await issueSessionToken({
    request: page.request,
    steamid64: randomSteamid64(),
    isSuperuser: false,
    name: fallbackName,
  })

  await page.request.put(`${apiUrl}/api/v1/players/${aliasPlayer.steamid64}`, {
    headers: {
      Authorization: `Bearer ${aliasPlayer.accessToken}`,
    },
    data: {
      alias: aliasName,
      country: "DE",
    },
  })

  await logInUser(page, superUserSteamid64, {
    isSuperuser: true,
    name: "Super User",
  })
  await page.goto("/admin/players")

  await expect(page.getByText(aliasName)).toBeVisible()
  await expect(page.getByText(fallbackName)).toBeVisible()
  await expect(page.getByAltText(`${aliasName} avatar`)).toBeVisible()

  await page.getByTestId(`country-flag-${aliasPlayer.steamid64}`).hover()
  await expect(page.getByText("Germany")).toBeVisible()

  await expect(
    page.getByTestId(`country-flag-${fallbackPlayer.steamid64}`),
  ).toHaveCount(0)
})
