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

    await page.goto("/admin/tournaments")
    await expect(page).not.toHaveURL(/\/admin\/tournaments$/)

    await page.goto("/admin/settings")
    await expect(page).not.toHaveURL(/\/admin\/settings$/)
  })
})

test("Superusers can manage public server visibility", async ({ page }) => {
  const serverId = "01966858-7280-7000-8000-000000000020"
  let isPublic = true
  let requestedVisibility: string | null = null

  await page.route("**/v1/admin/servers/access", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        role: "root_admin",
        can_approve_servers: true,
        owned_group_count: 0,
      }),
    })
  })
  await page.route("**/v1/admin/servers/groups", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })
  await page.route(
    /\/v1\/admin\/servers\/public(?:\/[^/?]+)?(?:\?.*)?$/,
    async (route) => {
      const url = new URL(route.request().url())
      if (route.request().method() === "PATCH") {
        const body = route.request().postDataJSON() as { is_public: boolean }
        isPublic = body.is_public
      } else {
        requestedVisibility = url.searchParams.get("is_public")
      }

      const server = {
        id: serverId,
        group_id: null,
        ip: "203.0.113.20",
        port: 27015,
        status: "enabled",
        is_public: isPublic,
        country: "DE",
        city: "Berlin",
        region: "EU",
        source: { type: "manual" },
        last_discovered_at: null,
        map_tier: 3,
        created_at: "2026-09-14T10:00:00Z",
        updated_at: "2026-09-14T10:00:00Z",
        group: null,
        live_status: {
          hostname: "Visibility Test Server",
          map: "kz_testmap",
          player_count: 0,
          max_players: 24,
          players: [],
          is_online: true,
          state: {},
          updated_at: "2026-09-14T10:00:00Z",
        },
      }
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          route.request().method() === "PATCH"
            ? server
            : { data: [server], count: 1 },
        ),
      })
    },
  )

  const { accessToken } = await issueSessionToken({
    request: page.request,
    steamid64: randomSteamid64(),
    roles: ["superuser"],
    name: "Server Admin",
  })
  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, accessToken)
  await page.goto("/admin/servers/public-server")

  await expect(
    page.getByRole("columnheader", { name: "Visibility" }),
  ).toBeVisible()
  await expect(page.getByText("Public", { exact: true })).toBeVisible()

  await page.getByRole("button", { name: "Edit public server" }).click()
  await page.getByRole("combobox", { name: "Server visibility" }).click()
  await page.getByRole("option", { name: "Hidden" }).click()
  await page.getByRole("button", { name: "Save public server" }).click()

  await expect.poll(() => isPublic).toBe(false)
  await expect(page.getByText("Hidden", { exact: true })).toBeVisible()

  await page
    .getByRole("combobox", { name: "Filter servers by visibility" })
    .click()
  await page.getByRole("option", { name: "Hidden" }).click()
  await expect.poll(() => requestedVisibility).toBe("false")
})

test("Superusers can paginate server groups", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "test-access-token")
  })
  await page.route("**/v1/users/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        steamid64: "76561198000000000",
        roles: ["superuser"],
        is_active: true,
      }),
    })
  })

  const groups = Array.from({ length: 21 }, (_, index) => ({
    id: `01900000-0000-7000-8000-${String(index).padStart(12, "0")}`,
    name: index === 20 ? "Node KZ Server" : `Group ${index + 1}`,
    custom_id: index === 20 ? "clibing_of_japan" : `group_${index + 1}`,
    website: null,
    discord: null,
    steam_group: null,
    owner_steamid64: null,
    status: "validated",
    server_count: index === 20 ? 2 : 0,
    last_api_key_used_at: null,
    created_at: "2026-09-14T10:00:00Z",
    updated_at: "2026-09-14T10:00:00Z",
    api_key: `test-api-key-${index + 1}`,
  }))

  await page.route("**/v1/admin/servers/access", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        role: "root_admin",
        can_approve_servers: true,
        owned_group_count: 0,
      }),
    })
  })
  await page.route(/\/v1\/admin\/servers\/groups(?:\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const offset = Number(url.searchParams.get("offset") ?? 0)
    const limit = Number(url.searchParams.get("limit") ?? 50)
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: groups.slice(offset, offset + limit),
        count: groups.length,
      }),
    })
  })

  await page.goto("/admin/servers/server-group")

  await expect(page.getByText("Total 21 Groups")).toBeVisible()
  await expect(page.getByText("Node KZ Server", { exact: true })).toBeHidden()

  const pageInput = page.getByRole("spinbutton", {
    name: "Current page, 2 total pages",
  })
  await pageInput.fill("2")
  await pageInput.press("Enter")

  await expect(page.getByText("Node KZ Server", { exact: true })).toBeVisible()
  await expect(pageInput).toHaveValue("2")
})

test("Superusers can sort server groups in both directions", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "test-access-token")
  })
  await page.route("**/v1/users/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        steamid64: "76561198000000000",
        roles: ["superuser"],
        is_active: true,
      }),
    })
  })
  await page.route("**/v1/admin/servers/access", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        role: "root_admin",
        can_approve_servers: true,
        owned_group_count: 0,
      }),
    })
  })

  const group = (
    id: string,
    name: string,
    lastApiKeyUsedAt: string | null,
    createdAt: string,
    updatedAt: string,
  ) => ({
    id,
    name,
    custom_id: name.toLowerCase(),
    website: null,
    discord: null,
    steam_group: null,
    owner_steamid64: null,
    status: "validated",
    server_count: 0,
    last_api_key_used_at: lastApiKeyUsedAt,
    created_at: createdAt,
    updated_at: updatedAt,
    api_key: `test-api-key-${name}`,
  })
  const groups = [
    group(
      "01900000-0000-7000-8000-000000000001",
      "Alpha",
      null,
      "2026-09-03T10:00:00Z",
      "2026-09-01T10:00:00Z",
    ),
    group(
      "01900000-0000-7000-8000-000000000002",
      "Beta",
      "2026-09-03T10:00:00Z",
      "2026-09-01T10:00:00Z",
      "2026-09-02T10:00:00Z",
    ),
    group(
      "01900000-0000-7000-8000-000000000003",
      "Gamma",
      "2026-09-01T10:00:00Z",
      "2026-09-02T10:00:00Z",
      "2026-09-03T10:00:00Z",
    ),
  ]
  let updatedOwnerSteamid64: string | null | undefined

  await page.route("**/v1/graphql", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          searchPlayers: {
            count: 1,
            data: [
              {
                steamid64: "76561198000099999",
                displayName: "Picked Owner",
                name: "Picked Owner",
                alias: null,
                customId: null,
                avatarHash: null,
                country: "DE",
                primaryScope: "OVR",
                rating: 1000,
                roles: null,
                lastPlayedAt: null,
              },
            ],
          },
        },
      }),
    })
  })
  await page.route(/\/v1\/admin\/servers\/groups\/[^/?]+$/, async (route) => {
    const requestBody = route.request().postDataJSON() as {
      owner_steamid64?: string | null
    }
    updatedOwnerSteamid64 = requestBody.owner_steamid64
    const targetGroup = groups.find((group) =>
      route.request().url().endsWith(group.id),
    )
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ...targetGroup,
        owner_steamid64: updatedOwnerSteamid64,
      }),
    })
  })

  await page.route(/\/v1\/admin\/servers\/groups(?:\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const offset = Number(url.searchParams.get("offset") ?? 0)
    const limit = Number(url.searchParams.get("limit") ?? 50)
    const sortBy = url.searchParams.get("sort_by") ?? "name"
    const sortOrder = url.searchParams.get("sort_order") ?? "asc"
    const sortedGroups = [...groups].sort((left, right) => {
      const leftValue = left[sortBy as keyof typeof left]
      const rightValue = right[sortBy as keyof typeof right]
      if (leftValue == null) {
        return rightValue == null ? 0 : 1
      }
      if (rightValue == null) {
        return -1
      }
      const comparison = String(leftValue).localeCompare(String(rightValue))
      return sortOrder === "desc" ? -comparison : comparison
    })
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: sortedGroups.slice(offset, offset + limit),
        count: groups.length,
      }),
    })
  })
  await page.goto("/admin/servers/server-group")

  const groupNames = page.locator("tbody tr td:first-child > div")
  const expectOrder = async (names: string[]) => {
    await expect(groupNames).toHaveText(names)
  }

  const groupHeader = page.getByRole("button", { name: "Group", exact: true })
  await expectOrder(["Alpha", "Beta", "Gamma"])
  await groupHeader.click()
  await expectOrder(["Gamma", "Beta", "Alpha"])
  await groupHeader.click()
  await expectOrder(["Alpha", "Beta", "Gamma"])

  const lastUsedHeader = page.getByRole("button", {
    name: "Last API Key Used",
    exact: true,
  })
  await lastUsedHeader.click()
  await expectOrder(["Gamma", "Beta", "Alpha"])
  await lastUsedHeader.click()
  await expectOrder(["Beta", "Gamma", "Alpha"])

  const createdHeader = page.getByRole("button", {
    name: "Created",
    exact: true,
  })
  await createdHeader.click()
  await expectOrder(["Beta", "Gamma", "Alpha"])
  await createdHeader.click()
  await expectOrder(["Alpha", "Gamma", "Beta"])

  const updatedHeader = page.getByRole("button", {
    name: "Updated",
    exact: true,
  })
  await updatedHeader.click()
  await expectOrder(["Alpha", "Beta", "Gamma"])
  await updatedHeader.click()
  await expectOrder(["Gamma", "Beta", "Alpha"])

  const gammaRow = page.locator("tbody tr").filter({ hasText: "Gamma" })
  await gammaRow.getByRole("button", { name: "Edit server group" }).click()
  await page.getByRole("textbox", { name: "Owner" }).fill("Picked")
  await page.getByRole("button", { name: /Picked Owner/ }).click()
  await page.getByRole("button", { name: "Save" }).click()
  await expect.poll(() => updatedOwnerSteamid64).toBe("76561198000099999")
})

test("Superusers can open tournament management", async ({ page }) => {
  await page.route(/\/v1\/admin\/tournaments(\?.*)?$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          {
            id: "01988888-8888-7888-8888-888888888888",
            name: "2026 AXE Major",
            starts_on: "2026-08-01",
            ends_on: "2026-08-03",
            official_url: null,
            level: "S",
            created_at: "2026-08-01T00:00:00Z",
            updated_at: "2026-08-01T00:00:00Z",
          },
        ],
        count: 1,
      }),
    })
  })
  await page.route(
    /\/v1\/admin\/tournaments\/achievements(\?.*)?$/,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
      })
    },
  )
  await logInUser(page, randomSteamid64(), {
    roles: ["superuser"],
    name: "Tournament Admin",
  })

  await page.goto("/admin/tournaments")
  await expect(page.getByRole("heading", { name: "Tournaments" })).toBeVisible()
  await expect(page.getByText("2026 AXE Major", { exact: true })).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Assign Achievement" }),
  ).toBeEnabled()
})

test("Superusers can manage the QQ binding secret", async ({ page }) => {
  const secrets = ["first-qq-binding-secret", "rotated-qq-binding-secret"]
  let configured = false
  let currentSecret = ""
  let secretIndex = 0

  await page.addInitScript(() => {
    Object.defineProperty(window, "__copiedText", {
      configurable: true,
      writable: true,
      value: "",
    })
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (text: string) => {
          ;(window as typeof window & { __copiedText: string }).__copiedText =
            text
        },
      },
    })
  })
  await page.route(
    /\/v1\/admin\/settings\/qq-binding-secret(?:\/.*)?$/,
    async (route) => {
      const url = new URL(route.request().url())
      const method = route.request().method()
      if (method === "GET" && url.pathname.endsWith("/reveal")) {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ secret: currentSecret }),
        })
        return
      }
      if (method === "GET") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            configured,
            created_at: configured ? "2026-08-24T12:00:00Z" : null,
            updated_at: configured ? "2026-08-24T12:00:00Z" : null,
          }),
        })
        return
      }
      if (method === "DELETE") {
        configured = false
        currentSecret = ""
        await route.fulfill({ status: 204 })
        return
      }
      currentSecret = secrets[secretIndex] ?? secrets[1]
      secretIndex += 1
      configured = true
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ secret: currentSecret }),
      })
    },
  )
  await logInUser(page, randomSteamid64(), { roles: ["superuser"] })
  await page.goto("/admin/settings")

  await expect(page.getByText("Not configured")).toBeVisible()
  await page.getByRole("button", { name: "Generate secret" }).click()
  await expect(page.getByTestId("admin-qq-binding-secret")).toHaveValue(
    secrets[0],
  )
  await page.getByTestId("admin-qq-binding-secret-copy-button").click()
  await expect
    .poll(() =>
      page.evaluate(
        () => (window as typeof window & { __copiedText: string }).__copiedText,
      ),
    )
    .toBe(secrets[0])

  await page.getByRole("button", { name: "Rotate secret" }).click()
  await expect(page.getByRole("dialog")).toContainText(
    "Rotate QQ binding secret?",
  )
  await page.getByRole("button", { name: "Rotate secret" }).last().click()
  await expect(page.getByTestId("admin-qq-binding-secret")).toHaveValue(
    secrets[1],
  )

  await page.getByRole("button", { name: "Revoke secret" }).click()
  await expect(page.getByRole("dialog")).toContainText(
    "Revoke QQ binding secret?",
  )
  await page.getByRole("button", { name: "Revoke secret" }).last().click()
  await expect(page.getByText("Not configured")).toBeVisible()
})

test("Superusers can manage application settings", async ({ page }) => {
  let location: "navbar" | "footer" = "navbar"
  let recordsSyncEnabled = true

  await page.route("**/v1/users/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        steamid64: randomSteamid64(),
        roles: ["superuser"],
        is_active: true,
        player: null,
      }),
    })
  })
  await page.route("**/v1/app-settings", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ community_links_location: location }),
    })
  })
  await page.route("**/v1/admin/settings/app", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as {
        community_links_location?: "navbar" | "footer"
        globalapi_records_sync_enabled?: boolean
      }
      location = body.community_links_location ?? location
      recordsSyncEnabled =
        body.globalapi_records_sync_enabled ?? recordsSyncEnabled
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        community_links_location: location,
        globalapi_records_sync_enabled: recordsSyncEnabled,
      }),
    })
  })
  await page.route("**/v1/admin/settings/qq-binding-secret", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        configured: false,
        created_at: null,
        updated_at: null,
      }),
    })
  })

  await page.addInitScript(() => {
    localStorage.setItem("access_token", "mock-superuser-token")
  })
  await page.goto("/admin/settings")

  const placementSwitch = page.getByRole("switch", {
    name: "Show community links in navbar",
  })
  await expect(placementSwitch).toBeChecked()
  const recordsSyncSwitch = page.getByRole("switch", {
    name: "Sync records from GlobalAPI",
  })
  await expect(recordsSyncSwitch).toBeChecked()
  await expect(
    page.locator("header").getByRole("link", { name: "Join Discord" }),
  ).toBeVisible()
  await expect(
    page.locator("footer").getByRole("link", { name: "Join us on Discord" }),
  ).toHaveCount(0)

  await placementSwitch.click()
  await expect.poll(() => location).toBe("footer")
  await expect(placementSwitch).not.toBeChecked()
  await expect(
    page.locator("header").getByRole("link", { name: "Join Discord" }),
  ).toHaveCount(0)
  await expect(
    page.locator("footer").getByRole("link", { name: "Join us on Discord" }),
  ).toBeVisible()

  await recordsSyncSwitch.click()
  await expect.poll(() => recordsSyncEnabled).toBe(false)
  await expect(recordsSyncSwitch).not.toBeChecked()

  await recordsSyncSwitch.click()
  await expect.poll(() => recordsSyncEnabled).toBe(true)
  await expect(recordsSyncSwitch).toBeChecked()

  await page.evaluate(() => localStorage.setItem("gokz-language", "zh-CN"))
  await page.reload()
  await expect(
    page.locator("footer").getByRole("link", { name: "加入我们的 QQ 群" }),
  ).toBeVisible()
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
  const settingsLink = adminSubmenu.getByRole("link", {
    name: "Settings",
    exact: true,
  })

  await expect(adminButton).toBeVisible()
  await expect(mapsLink).toHaveCount(0)
  await expect(settingsLink).toHaveCount(0)

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
  await expect(settingsLink).toBeVisible()
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
  let requestedSortBy: string | null = null
  let requestedSortOrder: string | null = null

  await page.route(/\/v1\/admin\/maps(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    requestedSortBy = url.searchParams.get("sort_by")
    requestedSortOrder = url.searchParams.get("sort_order")
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
  await expect
    .poll(() => ({ sortBy: requestedSortBy, sortOrder: requestedSortOrder }))
    .toEqual({
      sortBy: "created_at",
      sortOrder: "desc",
    })
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
