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

  await page.goto("/admin/player-sessions")
  await expect(page).toHaveURL(/\/admin\/player-sessions$/)
  await expect(adminButton).toHaveAttribute("data-active", "true")

  await page.goto("/admin/maps")
  await expect(page).toHaveURL(/\/admin\/maps$/)
  await expect(adminButton).toHaveAttribute("data-active", "true")
})

test("Superuser can access users, players, player sessions, and maps admin pages", async ({
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

  await page.goto("/admin/player-sessions")
  await expect(
    page.getByRole("heading", { name: /Player Sessions/ }),
  ).toBeVisible()
  await expect(
    page.getByRole("switch", { name: "Latest session per player" }),
  ).toBeVisible()

  await page.goto("/admin/maps")
  await expect(page.getByRole("heading", { name: "Maps" })).toBeVisible()
})

test.describe("Admin page access control", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Non-superuser cannot access users, players, player sessions, or maps admin pages", async ({
    page,
  }) => {
    await logInUser(page, randomSteamid64(), { isSuperuser: false })

    await page.goto("/admin/users")
    await expect(page).not.toHaveURL(/\/admin\/users$/)

    await page.goto("/admin/players")
    await expect(page).not.toHaveURL(/\/admin\/players$/)

    await page.goto("/admin/player-sessions")
    await expect(page).not.toHaveURL(/\/admin\/player-sessions$/)

    await page.goto("/admin/maps")
    await expect(page).not.toHaveURL(/\/admin\/maps$/)
  })
})

test("Superuser can view player sessions, filter latest sessions, and reveal IPs", async ({
  page,
}) => {
  let latestOnly = false

  await page.route(/\/v1\/admin\/player-sessions(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    latestOnly = url.searchParams.get("latest_only") === "true"
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          adminPlayerSessionPayload({
            latestOnly,
            sessionId: "01966858-7280-7000-8000-000000000001",
          }),
        ],
        count: latestOnly ? 1 : 2,
      }),
    })
  })

  await page.goto("/admin/player-sessions")

  await expect(
    page.getByRole("heading", { name: /Player Sessions/ }),
  ).toBeVisible()
  await expect(page.getByText("Session Runner")).toBeVisible()
  await expect(page.getByText("Session Group")).toBeVisible()
  await expect(page.getByText("kz_session_admin")).toBeVisible()
  await expect(page.getByText("***.***.***.***")).toBeVisible()
  await expect(page.getByText("192.0.2.42")).toHaveCount(0)

  await page
    .getByRole("button", {
      name: /Reveal IP for session 01966858-7280-7000-8000-000000000001/,
    })
    .click()
  await expect(page.getByText("192.0.2.42")).toBeVisible()
  await page
    .getByRole("button", {
      name: /Hide IP for session 01966858-7280-7000-8000-000000000001/,
    })
    .click()
  await expect(page.getByText("***.***.***.***")).toBeVisible()
  await expect(page.getByText("192.0.2.42")).toHaveCount(0)

  await page.getByRole("switch", { name: "Latest session per player" }).click()
  await expect(
    page.getByRole("switch", { name: "Latest session per player" }),
  ).toHaveAttribute("aria-checked", "true")
  await expect.poll(() => latestOnly).toBe(true)
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

function adminPlayerSessionPayload({
  latestOnly,
  sessionId,
}: {
  latestOnly: boolean
  sessionId: string
}) {
  return {
    id: sessionId,
    player: {
      steamid64: "76561198012345678",
      name: "Session Runner",
      alias: null,
      custom_id: null,
      avatar_hash: "abcdef",
      country: "DE",
      created_at: "2026-04-01T00:00:00Z",
      last_played_at: "2026-04-28T12:00:00Z",
      updated_at: "2026-04-28T12:00:00Z",
      is_website_user: false,
      profile_views: 0,
    },
    server_group_id: "01966858-7280-7000-8000-000000000010",
    server_group_name: "Session Group",
    connected_at: latestOnly ? "2026-04-28T14:00:00Z" : "2026-04-28T12:00:00Z",
    disconnect_at: "2026-04-28T14:30:00Z",
    last_heartbeat_at: "2026-04-28T14:30:00Z",
    ip_address: "192.0.2.42",
    map_name: "kz_session_admin",
    duration_seconds: 1800,
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
