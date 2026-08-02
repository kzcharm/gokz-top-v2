import { expect, test } from "@playwright/test"

import { COMMUNITY_LINKS } from "../src/lib/community-links"

test.use({ storageState: { cookies: [], origins: [] } })

function buildBan(index: number, source: "globalapi" | "manual" = "globalapi") {
  return {
    uuid: `01966858-7280-7000-8000-${index.toString().padStart(12, "0")}`,
    id: source === "globalapi" ? index : null,
    ban_type: source === "globalapi" ? "bhop_hack" : "bhop_macro",
    created_at: "2026-03-01T12:00:00Z",
    expires_at: null,
    notes: `Ban note ${index}`,
    player: {
      steamid64: `765611980000${index.toString().padStart(5, "0")}`,
      display_name: `Banned Player ${index}`,
    },
    stats: null,
  }
}

function buildGraphqlPlayer(
  steamid64: string,
  displayName: string,
  country = "DE",
) {
  return {
    steamid64,
    displayName,
    name: displayName,
    alias: null,
    customId: null,
    avatarHash: null,
    country,
    primaryScope: "OVR",
    rating: 1000,
    roles: null,
    lastPlayedAt: null,
  }
}

async function stubGraphqlPlayers(page: Parameters<typeof test>[0]["page"]) {
  await page.route("**/v1/graphql", async (route) => {
    const body = route.request().postDataJSON() as
      | {
          query?: string
          variables?: {
            q?: string
            steamid64s?: string[]
          }
        }
      | undefined
    const query = body?.query ?? ""

    if (query.includes("searchPlayers")) {
      const q = body?.variables?.q?.trim() ?? ""
      const player =
        q.length > 0
          ? buildGraphqlPlayer("76561198000099999", "Picked Player")
          : null
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            searchPlayers: {
              count: player ? 1 : 0,
              data: player ? [player] : [],
            },
          },
        }),
      })
      return
    }

    const steamid64s = body?.variables?.steamid64s ?? []
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          players: steamid64s.map((steamid64) =>
            steamid64 === "76561198000000042"
              ? buildGraphqlPlayer(steamid64, "Viewer")
              : steamid64 === "76561198000099999"
                ? buildGraphqlPlayer(steamid64, "Picked Player")
                : buildGraphqlPlayer(
                    steamid64,
                    `Banned Player ${steamid64.slice(-1)}`,
                  ),
          ),
        },
      }),
    })
  })
}

async function stubAuthedViewer(
  page: Parameters<typeof test>[0]["page"],
  roles: string[],
) {
  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem("gokz-datetime-format", "iso")
    localStorage.setItem("access_token", "test-access-token")
  })

  await page.route("**/v1/users/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        steamid64: "76561198000000042",
        roles,
        player: {
          steamid64: "76561198000000042",
          name: "Viewer",
          alias: null,
          custom_id: null,
          avatar_hash: null,
          country: "DE",
          created_at: null,
          last_played_at: null,
          updated_at: null,
          profile_views: 0,
        },
      }),
    })
  })

  await page.route(/\/v1\/players\/[^/]+\/friends$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: [],
        count: 0,
        sync: {
          visibility: null,
          last_checked_at: null,
          last_attempted_at: null,
          next_allowed_at: null,
        },
      }),
    })
  })

  await page.route(/\/v1\/players\/[^/]+\/follow-summary$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        viewer_is_following: false,
        viewer_is_self: false,
      }),
    })
  })
}

test("Bans table supports WASD pagination shortcuts without affecting typing", async ({
  page,
}) => {
  const banRequests: Array<{ offset: string | null; limit: string | null }> = []

  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem("gokz-datetime-format", "iso")
  })

  await page.route(/\/v1\/bans(?:\/[^?]+)?(?:\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const offset = Number(url.searchParams.get("offset") ?? "0")
    const limit = Number(url.searchParams.get("limit") ?? "20")
    banRequests.push({
      offset: url.searchParams.get("offset"),
      limit: url.searchParams.get("limit"),
    })

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        count: 45,
        data: Array.from({ length: Math.min(limit, 45 - offset) }, (_, index) =>
          buildBan(offset + index + 1),
        ),
      }),
    })
  })

  await page.route("**/v1/graphql", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          searchPlayers: {
            count: 0,
            data: [],
          },
        },
      }),
    })
  })

  await page.goto("/bans")

  await expect(page.getByText("Banned Player 1", { exact: true })).toBeVisible()
  await expect
    .poll(() => banRequests.at(-1))
    .toEqual({ offset: "0", limit: "20" })

  await page.keyboard.press("KeyD")
  await expect(
    page.getByText("Banned Player 21", { exact: true }),
  ).toBeVisible()
  await expect
    .poll(() => banRequests.at(-1))
    .toEqual({ offset: "20", limit: "20" })

  const searchBox = page.getByRole("textbox", { name: "Search players" })
  await searchBox.focus()
  await page.keyboard.press("KeyA")
  await expect(searchBox).toHaveValue("a")
  await expect(
    page.getByText("Banned Player 21", { exact: true }),
  ).toBeVisible()
  await expect
    .poll(() => banRequests.at(-1))
    .toEqual({ offset: "20", limit: "20" })

  await searchBox.fill("")
  await searchBox.evaluate((element) => {
    element.blur()
  })

  await page.keyboard.press("KeyA")
  await expect(page.getByText("Banned Player 1", { exact: true })).toBeVisible()
})

test("Bans page reads q from the URL, sends it to the API, and expands one match", async ({
  page,
}) => {
  const banRequests: Array<string | null> = []
  const matchedBan = {
    ...buildBan(42),
    stats: "Exact ban evidence",
  }

  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem("gokz-datetime-format", "iso")
  })

  await page.route(/\/v1\/bans(?:\/[^?]+)?(?:\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    banRequests.push(url.searchParams.get("q"))

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        count: url.searchParams.get("q") ? 1 : 0,
        data: url.searchParams.get("q") ? [matchedBan] : [],
      }),
    })
  })

  await page.route("**/v1/graphql", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          searchPlayers: {
            count: 0,
            data: [],
          },
        },
      }),
    })
  })

  await page.goto(`/bans?q=${matchedBan.uuid}`)

  await expect(page.getByRole("textbox", { name: "Search bans" })).toHaveValue(
    matchedBan.uuid,
  )
  await expect(
    page.getByText("Banned Player 42", { exact: true }),
  ).toBeVisible()
  await expect(page.getByText("Exact ban evidence")).toBeVisible()
  await expect.poll(() => banRequests.at(-1)).toBe(matchedBan.uuid)

  await page.getByRole("textbox", { name: "Search bans" }).fill("765611")
  await expect(page).toHaveURL(/\/bans\?q=765611$/)
  await expect.poll(() => banRequests.includes("765611")).toBe(true)
})

test("Bans player filter keeps the selected player in the search input", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem("gokz-datetime-format", "iso")
  })
  await stubGraphqlPlayers(page)

  await page.route(/\/v1\/bans(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ count: 0, data: [] }),
    })
  })

  await page.goto("/bans")

  const playerSearch = page.getByRole("textbox", { name: "Search players" })
  await playerSearch.fill("picked")
  await page.getByText("Picked Player", { exact: true }).click()

  await expect(playerSearch).toHaveValue("Picked Player")
  await expect(
    playerSearch.locator("xpath=..").getByText("Picked Player", {
      exact: true,
    }),
  ).toBeVisible()
  await expect(page.getByText("Picked Player", { exact: true })).toHaveCount(1)
})

test("Bans page shows Add Ban flows to admins and refreshes after create", async ({
  page,
}) => {
  const createdBodies: Array<Record<string, unknown>> = []
  const selectedPlayerBanHistory = [
    {
      ...buildBan(700, "globalapi"),
      notes: "Previous bhop hack ban",
      player: {
        steamid64: "76561198000099999",
        display_name: "Picked Player",
      },
    },
    {
      ...buildBan(701, "manual"),
      expires_at: "2026-01-01T12:00:00Z",
      notes: "Older expired manual ban",
      player: {
        steamid64: "76561198000099999",
        display_name: "Picked Player",
      },
    },
  ]
  const banRows = [buildBan(1), buildBan(2)]

  await stubAuthedViewer(page, ["admin"])
  await stubGraphqlPlayers(page)

  await page.route(/\/v1\/bans(?:\/[^?]+)?(?:\?.*)?$/, async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>
      createdBodies.push(body)
      const createdBan = {
        ...buildBan(999, "manual"),
        id: null,
        uuid: "01966858-7280-7000-8000-000000009999",
        notes: "Admin-created local ban",
        stats: null,
        player: {
          steamid64: "76561198000099999",
          display_name: "Picked Player",
        },
        updated_by_steamid64: "76561198000000042",
      }
      banRows.unshift(createdBan)
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(createdBan),
      })
      return
    }

    const url = new URL(route.request().url())
    const offset = Number(url.searchParams.get("offset") ?? "0")
    const limit = Number(url.searchParams.get("limit") ?? "20")
    const steamid64 = url.searchParams.get("steamid64")

    if (steamid64 === "76561198000099999") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: selectedPlayerBanHistory.length,
          data: selectedPlayerBanHistory,
        }),
      })
      return
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        count: banRows.length,
        data: banRows.slice(offset, offset + limit),
      }),
    })
  })

  await page.goto("/bans")

  await expect(page.getByRole("button", { name: "Add Ban" })).toBeVisible()

  await page.getByRole("button", { name: "Add Ban" }).click()
  await expect(page.getByRole("heading", { name: "Add Ban" })).toBeVisible()

  await page.getByRole("textbox", { name: "Player" }).fill("picked")
  await page.getByText("Picked Player", { exact: true }).click()
  await expect(page.getByText("Ban History", { exact: true })).toBeVisible()
  await expect(
    page.getByText("Previous bhop hack ban", { exact: true }),
  ).toBeVisible()
  await expect(
    page.getByText("Older expired manual ban", { exact: true }),
  ).toBeVisible()
  await page.getByRole("combobox", { name: "Ban Type" }).click()
  await page.getByRole("option", { name: "Bhop Macro" }).click()
  await page.getByRole("combobox", { name: "Length" }).click()
  await page.getByRole("option", { name: "1 Month" }).click()
  await page
    .getByRole("textbox", { name: "Notes" })
    .fill("Admin-created local ban")
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Add Ban" })
    .click()

  await expect(page.getByRole("heading", { name: "Add Ban" })).toHaveCount(0)
  await expect(createdBodies).toHaveLength(1)
  await expect(createdBodies[0]).toMatchObject({
    steamid64: "76561198000099999",
    ban_type: "bhop_macro",
    notes: "Admin-created local ban",
  })
  expect(createdBodies[0].expires_at).toEqual(expect.any(String))
  expect(createdBodies[0]).not.toHaveProperty("stats")
  expect(createdBodies[0]).not.toHaveProperty("id")

  await expect(page.getByText("Picked Player", { exact: true })).toBeVisible()
  await expect(
    page.getByText("Admin-created local ban", { exact: true }),
  ).toBeVisible()

  await page
    .getByRole("link", { name: /Banned Player 1/ })
    .dispatchEvent("contextmenu")
  await page.getByRole("menuitem", { name: "Add Ban" }).click()
  await expect(page.getByRole("heading", { name: "Add Ban" })).toBeVisible()
})

test("Users without admin moderation rights do not see Add Ban entry points", async ({
  page,
}) => {
  const banRows = [
    {
      ...buildBan(1),
      server_id: 321,
      server: {
        id: 321,
        name: "KZCharm Public Server",
      },
    },
    buildBan(2),
  ]

  await stubAuthedViewer(page, [])
  await stubGraphqlPlayers(page)

  await page.route(/\/v1\/bans(?:\/[^?]+)?(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        count: banRows.length,
        data: banRows,
      }),
    })
  })

  await page.goto("/bans")

  await expect(page.getByRole("button", { name: "Add Ban" })).toHaveCount(0)
  await expect(page.getByRole("link", { name: "Report" })).toHaveAttribute(
    "href",
    COMMUNITY_LINKS.discord,
  )
  await expect(
    page.getByRole("columnheader", { name: "Updated By" }),
  ).toHaveCount(0)
  await expect(page.getByRole("columnheader", { name: "Server" })).toBeVisible()
  await expect(page.getByText("KZCharm Public Server")).toBeVisible()
})

test("Chinese users get the QQ report link on the bans page", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem("gokz-datetime-format", "iso")
    localStorage.setItem("gokz-language", "zh-CN")
  })

  await page.route(/\/v1\/bans(?:\/[^?]+)?(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        count: 0,
        data: [],
      }),
    })
  })

  await page.route("**/v1/graphql", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          searchPlayers: {
            count: 0,
            data: [],
          },
        },
      }),
    })
  })

  await page.goto("/bans")

  await expect(page.getByRole("link", { name: "Report" })).toHaveAttribute(
    "href",
    COMMUNITY_LINKS.qq,
  )
})

test("Admins see updater and can edit and unban bans directly", async ({
  page,
}) => {
  const patchBodies: Array<Record<string, unknown>> = []
  const banRows = [
    {
      ...buildBan(1, "manual"),
      notes: "Needs update",
      updated_by_steamid64: "76561198000000042",
      updated_by_player: {
        steamid64: "76561198000000042",
        display_name: "Viewer",
      },
    },
  ]

  await stubAuthedViewer(page, ["admin"])
  await stubGraphqlPlayers(page)

  await page.route(/\/v1\/bans(?:\/[^?]+)?(?:\?.*)?$/, async (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as Record<string, unknown>
      patchBodies.push(body)
      banRows[0] = {
        ...banRows[0],
        ban_type: String(body.ban_type),
        expires_at:
          typeof body.expires_at === "string" || body.expires_at === null
            ? body.expires_at
            : banRows[0].expires_at,
        notes: typeof body.notes === "string" ? body.notes : null,
      }
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(banRows[0]),
      })
      return
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        count: banRows.length,
        data: banRows,
      }),
    })
  })

  await page.goto("/bans")

  await expect(page.getByRole("button", { name: "Admin mode" })).toHaveCount(0)
  await expect(
    page.getByRole("columnheader", { name: "Updated By" }),
  ).toBeVisible()
  await expect(page.getByText("Viewer", { exact: true })).toBeVisible()

  await page.getByRole("button", { name: "Edit ban" }).click()
  await expect(page.getByRole("heading", { name: "Edit Ban" })).toBeVisible()

  await page.getByRole("combobox", { name: "Ban Type" }).click()
  await page.getByRole("option", { name: "Other" }).click()
  await page.getByRole("combobox", { name: "Length" }).click()
  await page.getByRole("option", { name: "1 Month" }).click()
  await page.getByRole("textbox", { name: "Notes" }).fill("Edited note")
  await page.getByRole("button", { name: "Save" }).click()

  await expect(patchBodies).toHaveLength(1)
  await expect(patchBodies[0]).toMatchObject({
    ban_type: "other",
    notes: "Edited note",
    expires_at: "2026-04-01T12:00:00.000Z",
  })
  await expect(page.getByText("Edited note", { exact: true })).toBeVisible()

  await page.getByRole("button", { name: "Edit ban" }).click()
  await page.getByRole("button", { name: "Unban" }).click()

  await expect(patchBodies).toHaveLength(2)
  expect(patchBodies[1].expires_at).toEqual("2026-02-28T12:00:00.000Z")
  await expect(page.getByText("Unbanned", { exact: true })).toBeVisible()
})

test("Superusers can directly delete local bans without external ids", async ({
  page,
}) => {
  const deletedBanUuids: string[] = []
  let banRows = [
    {
      ...buildBan(1, "globalapi"),
      notes: "Mirrored ban",
    },
    {
      ...buildBan(2, "manual"),
      notes: "Local ban",
    },
  ]

  await stubAuthedViewer(page, ["superuser"])
  await stubGraphqlPlayers(page)

  await page.route(/\/v1\/bans(?:\/[^?]+)?(?:\?.*)?$/, async (route) => {
    if (route.request().method() === "DELETE") {
      const uuid = route.request().url().split("/").at(-1)
      if (uuid) {
        deletedBanUuids.push(uuid)
        banRows = banRows.filter((ban) => ban.uuid !== uuid)
      }
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ message: "Ban deleted successfully" }),
      })
      return
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        count: banRows.length,
        data: banRows,
      }),
    })
  })

  page.on("dialog", (dialog) => {
    void dialog.accept()
  })

  await page.goto("/bans")

  await expect(page.getByRole("button", { name: "Admin mode" })).toHaveCount(0)
  await page
    .getByRole("row", { name: /Banned Player 1/ })
    .getByRole("button", { name: "Edit ban" })
    .click()
  await expect(page.getByRole("button", { name: "Delete" })).toHaveCount(0)
  await page.getByRole("button", { name: "Cancel" }).click()

  await page
    .getByRole("row", { name: /Banned Player 2/ })
    .getByRole("button", { name: "Edit ban" })
    .click()
  await page.getByRole("button", { name: "Delete" }).click()

  await expect.poll(() => deletedBanUuids).toEqual([buildBan(2, "manual").uuid])
  await expect(page.getByText("Banned Player 2", { exact: true })).toHaveCount(
    0,
  )
})
