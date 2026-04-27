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

test("Superuser sidebar groups admin users and players under admin", async ({
  page,
}) => {
  await page.goto("/")

  const adminButton = page.getByRole("button", { name: "Admin" })
  const adminSubmenu = page.locator('[data-sidebar="menu-sub"]')
  const mapsLink = adminSubmenu.getByRole("link", {
    name: "Maps",
    exact: true,
  })

  await expect(adminButton).toBeVisible()
  await expect(mapsLink).toHaveCount(0)

  await adminButton.click()

  await expect(adminButton).toHaveAttribute("aria-expanded", "true")

  await page.goto("/admin/users")
  await expect(page).toHaveURL(/\/admin\/users$/)
  await expect(adminButton).toHaveAttribute("data-active", "true")

  await page.goto("/admin/players")
  await expect(page).toHaveURL(/\/admin\/players$/)
  await expect(adminButton).toHaveAttribute("data-active", "true")

  await page.goto("/admin/maps")
  await expect(page).toHaveURL(/\/admin\/maps$/)
  await expect(adminButton).toHaveAttribute("data-active", "true")
})

test("Superuser can access users, players, and maps admin pages", async ({
  page,
}) => {
  await page.goto("/admin/users")
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible()
  await expect(
    page.getByRole("textbox", { name: "Search users" }),
  ).toBeVisible()

  await page.goto("/admin/players")
  await expect(page.getByRole("heading", { name: "Players" })).toBeVisible()
  await expect(
    page.getByRole("textbox", { name: "Search players" }),
  ).toBeVisible()

  await page.goto("/admin/maps")
  await expect(page.getByRole("heading", { name: "Maps" })).toBeVisible()
})

test.describe("Admin page access control", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Non-superuser cannot access users, players, or maps admin pages", async ({
    page,
  }) => {
    await logInUser(page, randomSteamid64(), { isSuperuser: false })

    await page.goto("/admin/users")
    await expect(page).not.toHaveURL(/\/admin\/users$/)

    await page.goto("/admin/players")
    await expect(page).not.toHaveURL(/\/admin\/players$/)

    await page.goto("/admin/maps")
    await expect(page).not.toHaveURL(/\/admin\/maps$/)
  })
})

test("Superuser can manage map validation and 128-tick record filter tiers", async ({
  page,
}) => {
  const mapId = 991020
  const recordFilterId = 99102002
  let validated = false
  let tier: number | null = 3

  await page.route(/\/v1\/admin\/maps(\?.*)?$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: [adminMapPayload({ mapId, validated })],
        count: 1,
      }),
    })
  })

  await page.route(/\/v1\/admin\/maps\/\d+$/, async (route) => {
    const body = route.request().postDataJSON() as { validated: boolean }
    validated = body.validated
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(adminMapPayload({ mapId, validated })),
    })
  })

  await page.route(
    /\/v1\/admin\/maps\/\d+\/record-filters(\?.*)?$/,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          map_id: mapId,
          stages: [
            {
              stage: 0,
              record_filters: [
                adminRecordFilterPayload({ mapId, recordFilterId, tier }),
              ],
            },
          ],
        }),
      })
    },
  )

  await page.route(/\/v1\/admin\/record-filters\/\d+$/, async (route) => {
    const body = route.request().postDataJSON() as { tier: number | null }
    tier = body.tier
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        adminRecordFilterPayload({ mapId, recordFilterId, tier }),
      ),
    })
  })

  await page.goto("/admin/maps")
  await expect(page.getByRole("heading", { name: "Maps" })).toBeVisible()
  await expect(page.getByText("kz_admin_filters")).toBeVisible()

  await page
    .getByRole("switch", { name: "Set kz_admin_filters validation" })
    .click()
  await expect(
    page.getByRole("switch", { name: "Set kz_admin_filters validation" }),
  ).toHaveAttribute("aria-checked", "true")

  await page
    .getByRole("button", { name: "Show record filters for kz_admin_filters" })
    .click()
  await expect(page.getByRole("heading", { name: "Main stage" })).toBeVisible()
  await expect(page.getByText(`#${recordFilterId}`)).toBeVisible()
  const recordFilterRow = page.getByRole("row", {
    name: `#${recordFilterId} KZT PRO`,
    exact: true,
  })
  await expect(recordFilterRow).toBeVisible()

  await page
    .getByRole("combobox", { name: `Tier for record filter ${recordFilterId}` })
    .click()
  await page.getByRole("option", { name: "Tier 6" }).click()
  await page.getByRole("button", { name: "Save" }).click()
  await expect(
    page.getByRole("combobox", {
      name: `Tier for record filter ${recordFilterId}`,
    }),
  ).toContainText("Tier 6")
})

function adminMapPayload({
  mapId,
  validated,
}: {
  mapId: number
  validated: boolean
}) {
  return {
    id: mapId,
    name: "kz_admin_filters",
    filesize: 123456,
    validated,
    tiers: { OVR: 3, KZT: 3, SKZ: 4, VNL: null },
    difficulty: 3,
    created_on: "2021-01-01T00:00:00Z",
    updated_on: "2021-01-02T00:00:00Z",
    approved_by_steamid64: validated ? `${superUserSteamid64}` : "0",
    workshop_id: 1986459033,
    synced_at: "2021-01-03T00:00:00Z",
  }
}

function adminRecordFilterPayload({
  mapId,
  recordFilterId,
  tier,
}: {
  mapId: number
  recordFilterId: number
  tier: number | null
}) {
  return {
    id: recordFilterId,
    map_id: mapId,
    stage: 0,
    mode: "KZT",
    has_teleports: false,
    tier,
    created_on: "2021-01-01T00:00:00Z",
    updated_on: "2021-01-02T00:00:00Z",
    updated_by_id: `${superUserSteamid64}`,
  }
}

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
  const superUserToken = await issueSessionToken({
    request: page.request,
    steamid64: superUserSteamid64,
    isSuperuser: true,
    name: "Super User",
  })

  await page.request.put(`${apiUrl}/v1/players/${aliasPlayer.steamid64}`, {
    headers: {
      Authorization: `Bearer ${superUserToken.accessToken}`,
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
  await expect(
    page.getByTestId(`player-avatar-ring-${aliasPlayer.steamid64}`),
  ).toBeVisible()

  await page.getByTestId(`country-flag-${aliasPlayer.steamid64}`).hover()
  await expect(page.getByText("Germany")).toBeVisible()

  await expect(
    page.getByTestId(`country-flag-${fallbackPlayer.steamid64}`),
  ).toHaveCount(0)
})
