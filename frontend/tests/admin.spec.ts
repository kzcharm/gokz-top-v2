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

test.describe("Map admin access", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Map admin redirects to maps", async ({ page }) => {
    await logInUser(page, randomSteamid64(), {
      roles: ["map_admin"],
      name: "Map Admin",
    })

    await page.route(/\/v1\/admin\/maps(\?.*)?$/, async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
      })
    })

    await page.goto("/admin")
    await expect(page).toHaveURL(/\/admin\/maps$/)
    await expect(page.getByRole("heading", { name: "Maps" })).toBeVisible()

    const adminButton = page.getByRole("button", {
      name: "Admin",
      exact: true,
    })
    await expect(adminButton).toBeVisible()
    await expect(adminButton).toHaveAttribute("aria-expanded", "true")
  })

  test("Map admin cannot access superuser-only admin pages", async ({
    page,
  }) => {
    await logInUser(page, randomSteamid64(), {
      roles: ["map_admin"],
      name: "Map Admin",
    })

    await page.route(/\/v1\/admin\/maps(\?.*)?$/, async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
      })
    })

    await page.goto("/admin/users")
    await expect(page).not.toHaveURL(/\/admin\/users$/)

    await page.goto("/admin/players")
    await expect(page).not.toHaveURL(/\/admin\/players$/)

    await page.goto("/admin/player-sessions")
    await expect(page).not.toHaveURL(/\/admin\/player-sessions$/)

    await page.goto("/admin/player-social-links")
    await expect(page).not.toHaveURL(/\/admin\/player-social-links$/)
  })
})

test.describe("Server owner access", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Server owner redirects to servers", async ({ page }) => {
    await page.route(/\/v1\/admin\/servers\/access$/, async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "server_owner",
          can_approve_servers: false,
          owned_group_count: 0,
        }),
      })
    })
    await page.route(/\/v1\/admin\/servers\/groups$/, async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
      })
    })
    await page.route(
      /\/v1\/admin\/servers\/globalapi(\?.*)?$/,
      async (route) => {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ data: [], count: 0 }),
        })
      },
    )
    await page.route(/\/v1\/admin\/servers\/public(\?.*)?$/, async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
      })
    })

    await logInUser(page, randomSteamid64(), {
      roles: ["server_owner"],
      name: "Server Owner",
    })

    await page.goto("/admin")
    await expect(page).toHaveURL(/\/admin\/servers$/)
    await expect(page.getByRole("heading", { name: "Servers" })).toBeVisible()

    const adminButton = page.getByRole("button", {
      name: "Admin",
      exact: true,
    })
    await expect(adminButton).toBeVisible()
    await expect(adminButton).toHaveAttribute("aria-expanded", "true")
  })
})

test("Superuser sidebar groups admin users and players under admin", async ({
  page,
}) => {
  await page.goto("/")

  const adminButton = page.getByRole("button", {
    name: "Admin",
    exact: true,
  })
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

  await page.goto("/admin/player-social-links")
  await expect(page).toHaveURL(/\/admin\/player-social-links$/)
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

  await page.goto("/admin/player-social-links")
  await expect(
    page.getByRole("heading", { name: /Player Social Links/ }),
  ).toBeVisible()
})

test.describe("Admin page access control", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Non-superuser cannot access users, players, player sessions, or maps admin pages", async ({
    page,
  }) => {
    await logInUser(page, randomSteamid64(), { roles: [] })

    await page.goto("/admin/users")
    await expect(page).not.toHaveURL(/\/admin\/users$/)

    await page.goto("/admin/players")
    await expect(page).not.toHaveURL(/\/admin\/players$/)

    await page.goto("/admin/player-sessions")
    await expect(page).not.toHaveURL(/\/admin\/player-sessions$/)

    await page.goto("/admin/player-social-links")
    await expect(page).not.toHaveURL(/\/admin\/player-social-links$/)

    await page.goto("/admin/maps")
    await expect(page).not.toHaveURL(/\/admin\/maps$/)
  })
})

test.describe("Admin social links", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Superuser can view, add, edit, and delete player social links", async ({
    page,
  }) => {
    await logInUser(page, superUserSteamid64, {
      roles: ["superuser"],
      name: "Super User",
    })
    let links: unknown[] = []
    let requestedSortBy: string | null = null
    let requestedSortOrder: string | null = null

    await page.route(
      /\/v1\/admin\/player-social-links(\?.*)?$/,
      async (route) => {
        const method = route.request().method()
        if (method === "GET") {
          const url = new URL(route.request().url())
          requestedSortBy = url.searchParams.get("sort_by")
          requestedSortOrder = url.searchParams.get("sort_order")
        }
        if (method === "POST") {
          links = [
            {
              id: "019e0000-0000-7000-8000-000000000301",
              player_steamid64: "76561198012345678",
              player: {
                steamid64: "76561198012345678",
                display_name: "Social Admin",
              },
              platform: "github",
              account_identifier: "social-admin",
              verified: true,
              url: "https://github.com/social-admin",
              created_at: "2026-04-01T00:00:00Z",
              updated_at: "2026-04-01T00:00:00Z",
            },
          ]
          await route.fulfill({
            contentType: "application/json",
            body: JSON.stringify(links[0]),
          })
          return
        }
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )
    await page.route(
      /\/v1\/admin\/player-social-links\/[^/]+$/,
      async (route) => {
        const method = route.request().method()
        if (method === "PATCH") {
          links = [
            {
              ...(links[0] as object),
              verified: false,
              url: "https://github.com/social-admin-updated",
              account_identifier: "social-admin-updated",
            },
          ]
          await route.fulfill({
            contentType: "application/json",
            body: JSON.stringify(links[0]),
          })
          return
        }
        if (method === "DELETE") {
          links = []
          await route.fulfill({
            contentType: "application/json",
            body: JSON.stringify({
              message: "Social link deleted successfully",
            }),
          })
          return
        }
        await route.continue()
      },
    )

    await page.goto("/admin/player-social-links")
    await expect(
      page.getByRole("heading", { name: /Player Social Links/ }),
    ).toBeVisible()
    await expect
      .poll(() => ({ sortBy: requestedSortBy, sortOrder: requestedSortOrder }))
      .toEqual({
        sortBy: "created_at",
        sortOrder: "desc",
      })

    await page.getByRole("button", { name: "Add" }).click()
    const createDialog = page.getByRole("dialog", { name: "Add Social Link" })
    await createDialog.getByLabel("SteamID64").fill("76561198012345678")
    await createDialog.getByLabel("URL").fill("https://github.com/social-admin")
    await createDialog.getByRole("switch", { name: "Verified" }).click()
    await createDialog.getByRole("button", { name: "Save" }).click()
    await expect(page.getByText("social-admin")).toBeVisible()

    await page.getByRole("button", { name: "Edit social link" }).click()
    const editDialog = page.getByRole("dialog", { name: "Edit Social Link" })
    await editDialog
      .getByLabel("URL")
      .fill("https://github.com/social-admin-updated")
    await editDialog.getByRole("button", { name: "Save" }).click()
    await expect(page.getByText("social-admin-updated")).toBeVisible()
    await expect(
      page.getByRole("switch", {
        name: "Toggle verification for social-admin-updated",
      }),
    ).toHaveAttribute("aria-checked", "false")

    await page.getByRole("button", { name: "Delete social link" }).click()
    await expect(page.getByText("No social links found.")).toBeVisible()
  })
})

test("Superuser can view player sessions, filter latest sessions, and reveal IPs", async ({
  page,
}) => {
  let latestOnly = false
  let playerSteamid64Filter: string | null = null
  let serverGroupIdFilter: string | null = null

  await page.route(/\/v1\/admin\/player-sessions(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    latestOnly = url.searchParams.get("latest_only") === "true"
    playerSteamid64Filter = url.searchParams.get("player_steamid64")
    serverGroupIdFilter = url.searchParams.get("server_group_id")
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
  await page.route("**/v1/admin/servers/groups", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          {
            id: "01966858-7280-7000-8000-000000000010",
            name: "Session Group",
            custom_id: "session-group",
            status: "validated",
            api_key: "session-group-api-key",
            created_at: "2026-04-01T00:00:00Z",
            updated_at: "2026-04-28T12:00:00Z",
          },
        ],
        count: 1,
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

  await page.route("**/v1/players/search**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          adminPlayerSessionPayload({
            latestOnly,
            sessionId: "01966858-7280-7000-8000-000000000001",
          }).player,
        ],
        count: 1,
      }),
    })
  })
  await page.getByLabel("Filter sessions by player").fill("Session Runner")
  await page.getByText("Session Runner").last().click()
  await page.getByLabel("Filter sessions by server").click()
  await page.getByRole("option", { name: "Session Group" }).click()
  await expect.poll(() => playerSteamid64Filter).toBe("76561198012345678")
  await expect
    .poll(() => serverGroupIdFilter)
    .toBe("01966858-7280-7000-8000-000000000010")
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
  await page.getByRole("option", { name: "T6" }).click()
  await page.getByRole("button", { name: "Save" }).click()
  await expect(
    page.getByRole("combobox", {
      name: `Tier for record filter ${recordFilterId}`,
    }),
  ).toContainText("T6")
})

test("Superuser can edit a user and assign multiple roles", async ({
  page,
}) => {
  const targetSteamid64 = "76561198012345678"
  let userRoles: string[] = []
  let isActive = true

  await page.route(/\/v1\/users\/(\?.*)?$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          {
            steamid64: targetSteamid64,
            is_active: isActive,
            roles: userRoles,
            created_at: "2026-04-01T00:00:00Z",
            last_visited_at: "2026-04-02T00:00:00Z",
            player: {
              steamid64: targetSteamid64,
              display_name: "Role Target",
            },
          },
        ],
        count: 1,
      }),
    })
  })

  await page.route(/\/v1\/users\/76561198012345678$/, async (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as {
        is_active: boolean
        roles: string[]
      }
      isActive = body.is_active
      userRoles = body.roles
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          steamid64: targetSteamid64,
          is_active: isActive,
          roles: userRoles,
          created_at: "2026-04-01T00:00:00Z",
          last_visited_at: "2026-04-02T00:00:00Z",
          player: {
            steamid64: targetSteamid64,
            display_name: "Role Target",
          },
        }),
      })
      return
    }

    await route.continue()
  })

  await page.goto("/admin/users")
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible()

  await page
    .getByRole("button", { name: "Open actions for Role Target" })
    .click()
  await page.getByRole("menuitem", { name: "Edit User" }).click()

  await page.getByRole("checkbox", { name: "Superuser role" }).click()
  await page.getByRole("checkbox", { name: "Admin role" }).click()
  await page.getByRole("checkbox", { name: "Map Admin role" }).click()
  await page.getByRole("checkbox", { name: "Server Owner role" }).click()
  await page.getByRole("button", { name: "Save" }).click()

  const roleTargetRow = page.getByRole("row", { name: /Role Target/ })
  await expect(roleTargetRow.getByText("Superuser")).toBeVisible()
  await expect(roleTargetRow.getByText("Admin")).toBeVisible()
  await expect(roleTargetRow.getByText("Map Admin")).toBeVisible()
  await expect(roleTargetRow.getByText("Server Owner")).toBeVisible()
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
      roles: null,
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
    roles: [],
    name: `Source ${Date.now()}`,
  })
  const fallbackPlayer = await issueSessionToken({
    request: page.request,
    steamid64: randomSteamid64(),
    roles: [],
    name: fallbackName,
  })
  const superUserToken = await issueSessionToken({
    request: page.request,
    steamid64: superUserSteamid64,
    roles: ["superuser"],
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
    roles: ["superuser"],
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
