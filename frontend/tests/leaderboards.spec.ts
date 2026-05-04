import { expect, type Page, test } from "@playwright/test"

type GraphqlPlayer = {
  steamid64: string
  displayName: string
  name: string
  alias: string | null
  customId: string | null
  avatarHash: string | null
  country: string | null
  isWebsiteUser: boolean
  lastPlayedAt: string | null
}

function buildPlayerRef(steamid64: string, displayName: string) {
  return {
    steamid64,
    display_name: displayName,
  }
}

function buildGraphqlPlayer({
  steamid64,
  displayName,
  customId = null,
  country = null,
}: {
  steamid64: string
  displayName: string
  customId?: string | null
  country?: string | null
}): GraphqlPlayer {
  return {
    steamid64,
    displayName,
    name: displayName,
    alias: null,
    customId,
    avatarHash: null,
    country,
    isWebsiteUser: false,
    lastPlayedAt: null,
  }
}

async function stubPlayerGraphql(
  page: Page,
  {
    playersBySteamid64 = {},
    searchResultsByQuery = {},
    onPlayersQuery,
  }: {
    playersBySteamid64?: Record<string, GraphqlPlayer>
    searchResultsByQuery?: Record<string, GraphqlPlayer[]>
    onPlayersQuery?: (steamid64s: string[]) => void
  } = {},
) {
  await page.route("**/v1/graphql", async (route) => {
    const request = route.request()
    const body = request.postDataJSON() as {
      query?: string
      variables?: Record<string, unknown>
    }
    const query = body.query ?? ""
    const variables = body.variables ?? {}

    if (query.includes("searchPlayers")) {
      const q = String(variables.q ?? "").toLowerCase()
      const data = searchResultsByQuery[q] ?? []
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            searchPlayers: {
              count: data.length,
              data,
            },
          },
        }),
      })
      return
    }

    if (query.includes("players(")) {
      const steamid64s = Array.isArray(variables.steamid64s)
        ? (variables.steamid64s as string[])
        : []
      onPlayersQuery?.(steamid64s)
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            players: steamid64s.map(
              (steamid64) => playersBySteamid64[steamid64] ?? null,
            ),
          },
        }),
      })
      return
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ data: {} }),
    })
  })
}

async function stubRegions(page: Page) {
  await page.route("**/v1/regions/", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        count: 2,
        data: [
          { code: "EU", name: "Europe", country_codes: ["DE", "FR"] },
          { code: "AS", name: "Asia", country_codes: ["JP"] },
        ],
      }),
    })
  })
}

test.describe("Leaderboards page", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("renders leaderboard empty state", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.clear()
    })
    await stubRegions(page)
    await stubPlayerGraphql(page)
    await page.route("**/v1/leaderboards/players*", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          data: [],
          count: 0,
        }),
      })
    })

    await page.goto("/leaderboards/players")

    await expect(page.getByRole("tab", { name: "Players" })).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Find Me", exact: true }),
    ).toBeDisabled()
    await expect(
      page.getByRole("button", { name: "Select record scope" }),
    ).toContainText("OVR")
    await expect(page.getByText("No results found.")).toBeVisible()
  })

  test("hydrates visible leaderboard players with one batched graphql request", async ({
    page,
  }) => {
    const playerBatchRequests: string[][] = []

    await page.addInitScript(() => {
      localStorage.clear()
    })
    await stubRegions(page)
    await stubPlayerGraphql(page, {
      playersBySteamid64: {
        "76561198000000001": buildGraphqlPlayer({
          steamid64: "76561198000000001",
          displayName: "Alpha",
          country: "DE",
        }),
        "76561198000000002": buildGraphqlPlayer({
          steamid64: "76561198000000002",
          displayName: "Beta",
          country: "FR",
        }),
      },
      onPlayersQuery: (steamid64s) => {
        playerBatchRequests.push(steamid64s)
      },
    })
    await page.route("**/v1/leaderboards/players*", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 2,
          data: [
            {
              rank: 1,
              player: buildPlayerRef("76561198000000001", "Alpha"),
              rating: 1000,
              rating_easy: 500,
              rating_hard: 500,
              points: 2000,
              wrs_nub: 1,
              wrs_pro: 0,
              records_900_plus: 2,
              records_800_plus: 2,
              unique_map_finishes: 20,
            },
            {
              rank: 2,
              player: buildPlayerRef("76561198000000002", "Beta"),
              rating: 900,
              rating_easy: 450,
              rating_hard: 450,
              points: 1800,
              wrs_nub: 0,
              wrs_pro: 1,
              records_900_plus: 1,
              records_800_plus: 2,
              unique_map_finishes: 18,
            },
          ],
        }),
      })
    })

    await page.goto("/leaderboards")

    await expect(page.getByText("Alpha")).toBeVisible()
    await expect(page.getByText("Beta")).toBeVisible()
    await expect.poll(() => playerBatchRequests.length).toBe(1)
    expect(playerBatchRequests[0]).toEqual([
      "76561198000000001",
      "76561198000000002",
    ])
  })

  test("switching scope refetches leaderboard data", async ({ page }) => {
    const requestedScopes: string[] = []

    await page.addInitScript(() => {
      localStorage.clear()
    })
    await stubRegions(page)
    await stubPlayerGraphql(page)
    await page.route("**/v1/leaderboards/players*", async (route) => {
      const url = new URL(route.request().url())
      const scope = url.searchParams.get("scope") || "OVR"
      requestedScopes.push(scope)

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          data: [
            {
              rank: 1,
              player: buildPlayerRef("76561198000000001", `Scope ${scope}`),
              rating: 1000,
              rating_easy: 500,
              rating_hard: 500,
              points: 2000,
              wrs_nub: 1,
              wrs_pro: 0,
              records_900_plus: 2,
              records_800_plus: 2,
              unique_map_finishes: 20,
            },
          ],
        }),
      })
    })

    await page.goto("/leaderboards")
    await expect(page.getByText("Scope OVR")).toBeVisible()

    await page.getByRole("button", { name: "Select record scope" }).click()
    await page.getByRole("menuitemradio", { name: "KZT" }).click()

    await expect(
      page.getByRole("button", { name: "Select record scope" }),
    ).toContainText("KZT")
    await expect(page.getByText("Scope KZT")).toBeVisible()
    expect(requestedScopes).toContain("OVR")
    expect(requestedScopes).toContain("KZT")
  })

  test("searching and selecting a player jumps to their leaderboard page", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.clear()
    })
    await stubRegions(page)
    await stubPlayerGraphql(page, {
      playersBySteamid64: {
        "76561198000000002": buildGraphqlPlayer({
          steamid64: "76561198000000002",
          displayName: "Beta",
          customId: "beta",
        }),
        "76561198000000003": buildGraphqlPlayer({
          steamid64: "76561198000000003",
          displayName: "Gamma",
          customId: "gamma",
        }),
      },
      searchResultsByQuery: {
        beta: [
          buildGraphqlPlayer({
            steamid64: "76561198000000002",
            displayName: "Beta",
            customId: "beta",
          }),
        ],
        gamma: [
          buildGraphqlPlayer({
            steamid64: "76561198000000003",
            displayName: "Gamma",
            customId: "gamma",
          }),
        ],
      },
    })

    await page.route("**/v1/leaderboards/players/beta*", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          rank: 41,
          rating: 900,
        }),
      })
    })

    await page.route("**/v1/leaderboards/players*", async (route) => {
      const url = new URL(route.request().url())
      const offset = Number(url.searchParams.get("offset") || "0")
      const limit = Number(url.searchParams.get("limit") || "20")

      const data =
        offset === 40
          ? [
              {
                rank: 41,
                player: buildPlayerRef("76561198000000002", "Beta"),
                rating: 900,
                rating_easy: 450,
                rating_hard: 450,
                points: 1800,
                wrs_nub: 0,
                wrs_pro: 0,
                records_900_plus: 1,
                records_800_plus: 2,
                unique_map_finishes: 20,
              },
            ]
          : Array.from({ length: limit }, (_, index) => ({
              rank: offset + index + 1,
              player: buildPlayerRef(
                `76561198000000${(offset + index + 1).toString().padStart(3, "0")}`,
                `Player ${offset + index + 1}`,
              ),
              rating: 1000 - (offset + index),
              rating_easy: 500,
              rating_hard: 500,
              points: 2000,
              wrs_nub: 0,
              wrs_pro: 0,
              records_900_plus: 0,
              records_800_plus: 0,
              unique_map_finishes: 20,
            }))

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 45,
          data,
        }),
      })
    })

    await page.goto("/leaderboards")
    await expect(
      page.locator('tr[data-player-steamid64="76561198000000001"]'),
    ).toBeVisible()

    await page.getByRole("textbox", { name: "Search players" }).fill("Beta")
    await page
      .locator("button", { has: page.getByText("Beta", { exact: true }) })
      .first()
      .click()

    await expect(page.getByRole("row", { name: /41.*Beta/ })).toBeVisible()
    await expect(page.getByRole("row", { name: /41.*Beta/ })).toHaveClass(
      /leaderboard-self-spotlight/,
    )

    await page.getByRole("textbox", { name: "Search players" }).fill("Gamma")
    await expect(page.getByText("Gamma", { exact: true })).toBeVisible()
  })

  test("find me jumps to the signed-in player's leaderboard page", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.clear()
      localStorage.setItem("access_token", "header.payload.signature")
    })
    await stubRegions(page)
    await stubPlayerGraphql(page, {
      playersBySteamid64: {
        "76561198000000042": buildGraphqlPlayer({
          steamid64: "76561198000000042",
          displayName: "Find Me Player",
          country: "DE",
        }),
      },
    })

    await page.route("**/v1/users/me", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          steamid64: "76561198000000042",
          roles: [],
          player: {
            steamid64: "76561198000000042",
            name: "Find Me Player",
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

    await page.route(
      "**/v1/leaderboards/players/76561198000000042*",
      async (route) => {
        const url = new URL(route.request().url())
        expect(url.searchParams.get("country")).toBeNull()
        expect(url.searchParams.get("region")).toBeNull()
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            rank: 41,
            rating: 1100,
          }),
        })
      },
    )

    await page.route("**/v1/leaderboards/players*", async (route) => {
      const url = new URL(route.request().url())
      const offset = Number(url.searchParams.get("offset") || "0")
      const limit = Number(url.searchParams.get("limit") || "20")

      const data =
        offset === 40
          ? [
              {
                rank: 41,
                player: buildPlayerRef("76561198000000042", "Find Me Player"),
                rating: 1100,
                rating_easy: 550,
                rating_hard: 550,
                points: 2000,
                wrs_nub: 0,
                wrs_pro: 0,
                records_900_plus: 0,
                records_800_plus: 0,
                unique_map_finishes: 25,
              },
            ]
          : Array.from({ length: limit }, (_, index) => ({
              rank: offset + index + 1,
              player: buildPlayerRef(
                `76561198000000${(offset + index + 1).toString().padStart(3, "0")}`,
                `Player ${offset + index + 1}`,
              ),
              rating: 1000 - (offset + index),
              rating_easy: 500,
              rating_hard: 500,
              points: 1000,
              wrs_nub: 0,
              wrs_pro: 0,
              records_900_plus: 0,
              records_800_plus: 0,
              unique_map_finishes: 20,
            }))

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 45,
          data,
        }),
      })
    })

    await page.goto("/leaderboards")

    await expect(
      page.getByRole("button", { name: "Find Me", exact: true }),
    ).toBeEnabled()
    await page.getByRole("button", { name: "Find Me", exact: true }).click()

    await expect(
      page.getByRole("row", { name: /41.*Find Me Player/ }),
    ).toBeVisible()
    await expect(
      page.getByRole("row", { name: /41.*Find Me Player/ }),
    ).toHaveClass(/bg-primary\/10/)
    await expect(
      page.getByRole("row", { name: /41.*Find Me Player/ }),
    ).toHaveClass(/leaderboard-self-spotlight/)
  })

  test("country and region filters are mutually exclusive and affect requests", async ({
    page,
  }) => {
    const leaderboardRequests: Array<{
      country: string | null
      region: string | null
    }> = []
    const rankRequests: Array<{
      country: string | null
      region: string | null
    }> = []

    await page.addInitScript(() => {
      localStorage.clear()
      localStorage.setItem("access_token", "header.payload.signature")
    })
    await stubRegions(page)
    await stubPlayerGraphql(page, {
      playersBySteamid64: {
        "76561198000000042": buildGraphqlPlayer({
          steamid64: "76561198000000042",
          displayName: "Find Me Player",
          country: "DE",
        }),
      },
    })

    await page.route("**/v1/users/me", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          steamid64: "76561198000000042",
          roles: [],
          player: {
            steamid64: "76561198000000042",
            name: "Find Me Player",
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

    await page.route(
      "**/v1/leaderboards/players/76561198000000042*",
      async (route) => {
        const url = new URL(route.request().url())
        rankRequests.push({
          country: url.searchParams.get("country"),
          region: url.searchParams.get("region"),
        })
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            rank: 1,
            rank_regional: 1,
            rating: 1100,
          }),
        })
      },
    )

    await page.route("**/v1/leaderboards/players*", async (route) => {
      const url = new URL(route.request().url())
      leaderboardRequests.push({
        country: url.searchParams.get("country"),
        region: url.searchParams.get("region"),
      })
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          data: [
            {
              rank: 1,
              player: buildPlayerRef("76561198000000042", "Find Me Player"),
              rating: 1100,
              rating_easy: 550,
              rating_hard: 550,
              points: 2000,
              wrs_nub: 0,
              wrs_pro: 0,
              records_900_plus: 0,
              records_800_plus: 0,
              unique_map_finishes: 25,
            },
          ],
        }),
      })
    })

    await page.goto("/leaderboards")

    await page.getByRole("button", { name: "country" }).click()
    await page.getByRole("button", { name: "Germany" }).click()
    await expect
      .poll(() => leaderboardRequests.at(-1))
      .toEqual({ country: "DE", region: null })

    await page.getByRole("combobox").filter({ hasText: "region" }).click()
    await page.getByRole("option", { name: /^EU$/ }).click()
    await expect
      .poll(() => leaderboardRequests.at(-1))
      .toEqual({ country: null, region: "EU" })

    await page.getByRole("button", { name: "Find Me", exact: true }).click()
    await expect
      .poll(() => rankRequests.at(-1))
      .toEqual({ country: null, region: "EU" })
  })

  test("maps tab loads leaderboard data and applies sorting and filters", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.clear()
    })
    await stubRegions(page)
    await stubPlayerGraphql(page)
    await page.route("**/v1/leaderboards/players*", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          data: [],
          count: 0,
        }),
      })
    })
    await page.route("**/v1/leaderboards/maps*", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 3,
          data: [
            {
              map: { id: 1, name: "kz_alpha" },
              tier: 5,
              review_summary: {
                overall_avg: 4.7,
                gameplay_avg: 4.5,
                visuals_avg: 4.9,
                reviews_count: 10,
                gameplay_count: 10,
                visuals_count: 10,
                comments_count: 2,
                updated_at: "2099-01-01T00:00:00Z",
              },
              total_finishes: 15,
              total_playtime: 100,
              average_first_completion_time: 12,
              median_first_completion_time: 11,
              average_playtime_per_player: 10,
              median_playtime_per_player: 10,
              average_finishes_per_player: 1.5,
              median_finishes_per_player: 1.5,
              pro_nub_ratio: 0.4,
              unique_pro_finishes: 4,
              unique_nub_finishes: 10,
              updated_at: "2099-01-01T00:00:00Z",
            },
            {
              map: { id: 2, name: "kz_beta" },
              tier: 3,
              review_summary: {
                overall_avg: 4.1,
                gameplay_avg: 4.0,
                visuals_avg: 4.2,
                reviews_count: 8,
                gameplay_count: 8,
                visuals_count: 8,
                comments_count: 10,
                updated_at: "2099-01-01T00:00:00Z",
              },
              total_finishes: 8,
              total_playtime: 50,
              average_first_completion_time: 9,
              median_first_completion_time: 9,
              average_playtime_per_player: 10,
              median_playtime_per_player: 10,
              average_finishes_per_player: 1.6,
              median_finishes_per_player: 1.5,
              pro_nub_ratio: 0.4,
              unique_pro_finishes: 2,
              unique_nub_finishes: 5,
              updated_at: "2099-01-01T00:00:00Z",
            },
            {
              map: { id: 3, name: "kz_gamma" },
              tier: 5,
              review_summary: null,
              total_finishes: 1,
              total_playtime: 10,
              average_first_completion_time: 10,
              median_first_completion_time: 10,
              average_playtime_per_player: 10,
              median_playtime_per_player: 10,
              average_finishes_per_player: 1,
              median_finishes_per_player: 1,
              pro_nub_ratio: 1,
              unique_pro_finishes: 1,
              unique_nub_finishes: 1,
              updated_at: null,
            },
          ],
        }),
      })
    })

    await page.goto("/leaderboards")
    await page.getByRole("tab", { name: "Maps" }).click()

    await expect(page.getByText("kz_alpha")).toBeVisible()
    await expect(page.getByText("kz_beta")).toBeVisible()

    await page.getByRole("button", { name: "Ratings" }).click()
    await expect(
      page.locator("tbody tr").first().getByText("kz_alpha"),
    ).toBeVisible()

    await page
      .getByRole("combobox", { name: "Filter maps leaderboard by tier" })
      .click()
    await page.getByRole("option", { name: "T5" }).click()
    await expect(page.getByText("kz_beta")).not.toBeVisible()
    await expect(page.getByText("kz_alpha")).toBeVisible()
    await expect(page.getByText("kz_gamma")).toBeVisible()

    await page
      .getByRole("spinbutton", { name: "Minimum total playtime" })
      .fill("90")
    await expect(page.getByText("kz_alpha")).toBeVisible()
    await expect(page.getByText("kz_gamma")).not.toBeVisible()
  })
})
