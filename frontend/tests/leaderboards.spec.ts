import { expect, type Page, test } from "@playwright/test"
import type { ModeScope, UserRole } from "@/client"
import { issueSessionToken } from "./utils/privateApi"

type GraphqlPlayer = {
  steamid64: string
  displayName: string
  name: string
  alias: string | null
  customId: string | null
  avatarHash: string | null
  country: string | null
  primaryScope: ModeScope
  rating: number
  roles: UserRole[] | null
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
  primaryScope = "OVR",
  rating = 0,
}: {
  steamid64: string
  displayName: string
  customId?: string | null
  country?: string | null
  primaryScope?: ModeScope
  rating?: number
}): GraphqlPlayer {
  return {
    steamid64,
    displayName,
    name: displayName,
    alias: null,
    customId,
    avatarHash: null,
    country,
    primaryScope,
    rating,
    roles: null,
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
  await page.route("**/v1/regions", async (route) => {
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
    await page.getByRole("button", { name: "Friends" }).click()
    await expect(page.getByText("Login required")).toBeVisible()
    await expect(
      page.getByText("Log in first to view your friends leaderboard."),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Select record scope" }),
    ).toContainText("OVR")
    await expect(page.getByText("No results found.")).toBeVisible()
    await expect(page.getByText("Rows per page")).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Go to first page" }),
    ).toBeDisabled()
    await expect(
      page.getByRole("spinbutton", { name: "Current page, 1 total pages" }),
    ).toHaveValue("1")
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
      /bg-primary\/10/,
    )
    await expect(page.getByRole("row", { name: /41.*Beta/ })).toHaveClass(
      /leaderboard-self-spotlight/,
    )

    await page.getByRole("textbox", { name: "Search players" }).fill("Gamma")
    await expect(page.getByText("Gamma", { exact: true })).toBeVisible()
  })

  test("find me jumps to the signed-in player's leaderboard page", async ({
    page,
    request,
  }) => {
    const { accessToken } = await issueSessionToken({
      request,
      steamid64: "76561198000000042",
      name: "Find Me Player",
    })
    await page.addInitScript((token) => {
      localStorage.clear()
      localStorage.setItem("access_token", token)
    }, accessToken)
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

  test("friends only clears geography filters and sends viewer-scoped requests", async ({
    page,
    request,
  }) => {
    const leaderboardRequests: Array<{
      friendsOnly: string | null
      country: string | null
      region: string | null
    }> = []
    const rankRequests: Array<{
      friendsOnly: string | null
      country: string | null
      region: string | null
    }> = []

    const { accessToken } = await issueSessionToken({
      request,
      steamid64: "76561198000000042",
      name: "Find Me Player",
    })
    await page.addInitScript((token) => {
      localStorage.clear()
      localStorage.setItem("access_token", token)
    }, accessToken)
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
          friendsOnly: url.searchParams.get("friends_only"),
          country: url.searchParams.get("country"),
          region: url.searchParams.get("region"),
        })
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            rank: 1,
            global_rank: 41,
            rank_regional: 1,
            rating: 1100,
          }),
        })
      },
    )

    await page.route("**/v1/leaderboards/players*", async (route) => {
      const url = new URL(route.request().url())
      leaderboardRequests.push({
        friendsOnly: url.searchParams.get("friends_only"),
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
              global_rank: 41,
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
      .toEqual({ friendsOnly: null, country: "DE", region: null })

    await page.getByRole("button", { name: "Friends" }).click()
    await expect
      .poll(() => leaderboardRequests.at(-1))
      .toEqual({ friendsOnly: "true", country: null, region: null })

    await expect(page.getByRole("combobox")).toBeDisabled()
    await expect(page.getByRole("button", { name: "country" })).toBeDisabled()
    await expect(
      page.getByRole("row", { name: /1 \(41\).*Find Me Player/ }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Find Me", exact: true }).click()
    await expect
      .poll(() => rankRequests.at(-1))
      .toEqual({ friendsOnly: "true", country: null, region: null })
  })

  test("country and region filters are mutually exclusive and affect requests", async ({
    page,
    request,
  }) => {
    const leaderboardRequests: Array<{
      country: string | null
      region: string | null
    }> = []
    const rankRequests: Array<{
      country: string | null
      region: string | null
    }> = []

    const { accessToken } = await issueSessionToken({
      request,
      steamid64: "76561198000000042",
      name: "Find Me Player",
    })
    await page.addInitScript((token) => {
      localStorage.clear()
      localStorage.setItem("access_token", token)
    }, accessToken)
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
    await expect(page.getByText("Rows per page")).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Go to first page" }),
    ).toBeVisible()
    await expect(
      page.getByRole("spinbutton", { name: "Current page, 1 total pages" }),
    ).toHaveValue("1")

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

  test("jumpstats leaderboard defaults to long jump and refetches on scope change", async ({
    page,
  }) => {
    const requestedScopes: string[] = []
    const requestedTypes: string[] = []
    let playerLeaderboardRequests = 0

    await page.addInitScript(() => {
      localStorage.clear()
    })
    await page.route("**/v1/leaderboards/players*", async (route) => {
      playerLeaderboardRequests += 1
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
      })
    })
    await page.route("**/v1/leaderboards/jumpstats*", async (route) => {
      const url = new URL(route.request().url())
      const scope = url.searchParams.get("scope") || "OVR"
      const type = url.searchParams.get("type") || "LJ"
      requestedScopes.push(scope)
      requestedTypes.push(type)

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          data: [
            {
              rank: 1,
              id: "6a4ff955-7a2d-4b91-86f4-a7d493bbac31",
              player: buildPlayerRef("76561198000000001", `Scope ${scope}`),
              server_group_id: "eb8f4b1c-c83c-4f7d-8ef8-4d7c0dcdb2bb",
              server_group: {
                id: "eb8f4b1c-c83c-4f7d-8ef8-4d7c0dcdb2bb",
                name: "Jumpstats Group",
              },
              mode: scope === "SKZ" ? "SKZ" : "KZT",
              type,
              distance: 281.1234,
              block: 280,
              strafes: 8,
              sync_percent: 90,
              pre_speed: 275.22,
              max_speed: 366.78,
              jumped_at: "2099-01-01T00:00:00Z",
            },
          ],
        }),
      })
    })

    await page.goto("/leaderboards/jumpstats")

    await expect(page.getByText("Scope OVR")).toBeVisible()
    await expect(page.getByText("Jumpstats Group")).toBeVisible()
    await expect(page.getByText("Filters")).not.toBeVisible()
    await expect(page.getByText("Jump Type")).not.toBeVisible()
    await expect(
      page.getByRole("tab", { name: "Long Jump", exact: true }),
    ).toHaveAttribute("data-state", "active")
    await expect(
      page.getByRole("tab", { name: "Fall", exact: true }),
    ).toHaveCount(0)
    await expect(
      page.getByRole("tab", { name: "Unknown", exact: true }),
    ).toHaveCount(0)
    await expect(
      page.getByRole("tab", { name: "Invalid", exact: true }),
    ).toHaveCount(0)
    expect(requestedScopes[0]).toBe("OVR")
    expect(requestedTypes[0]).toBe("LJ")
    expect(playerLeaderboardRequests).toBe(0)

    await page.getByRole("button", { name: "Select record scope" }).click()
    await page.getByRole("menuitemradio", { name: "SKZ" }).click()

    await expect(page.getByText("Scope SKZ")).toBeVisible()
    expect(requestedScopes).toContain("SKZ")
  })

  test("jumpstats leaderboard refetches on jump type change and block toggle", async ({
    page,
  }) => {
    const requests: Array<{
      scope: string
      type: string
      sortBy: string | null
      sortOrder: string | null
    }> = []

    await page.addInitScript(() => {
      localStorage.clear()
    })
    await page.route("**/v1/leaderboards/jumpstats*", async (route) => {
      const url = new URL(route.request().url())
      const scope = url.searchParams.get("scope") || "OVR"
      const type = url.searchParams.get("type") || "LJ"
      const sortBy = url.searchParams.get("sort_by")
      const sortOrder = url.searchParams.get("sort_order")
      requests.push({ scope, type, sortBy, sortOrder })

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          data: [
            {
              rank: 1,
              id: "2e4bf9af-2e1a-4267-ab90-7f0ca1269ef6",
              player: buildPlayerRef("76561198000000002", "Beta"),
              server_group_id: "94db4edc-447c-4328-b5ca-1177c51d39c9",
              server_group: {
                id: "94db4edc-447c-4328-b5ca-1177c51d39c9",
                name: "Jumpstats Group",
              },
              mode: "KZT",
              type,
              distance: sortBy === "block" ? 283.5 : 280.5,
              block: 282,
              strafes: 7,
              sync_percent: 88,
              pre_speed: 274.11,
              max_speed: 365.41,
              jumped_at: "2099-01-01T00:00:00Z",
            },
          ],
        }),
      })
    })

    await page.goto("/leaderboards/jumpstats")

    await expect(
      page.getByRole("cell", { name: "7", exact: true }),
    ).toBeVisible()
    await expect(page.getByRole("columnheader", { name: "Block" })).toHaveCount(
      0,
    )
    await page.getByRole("tab", { name: "Bhop", exact: true }).click()
    await expect(page.getByText("Beta")).toBeVisible()
    expect(requests.some((request) => request.type === "BH")).toBe(true)

    await page.getByRole("button", { name: "Block" }).click()
    await expect(
      page.getByRole("columnheader", { name: "Block" }),
    ).toBeVisible()

    const blockRequests = requests.filter(
      (request) => request.sortBy === "block",
    )
    expect(blockRequests.length).toBeGreaterThan(0)
    expect(blockRequests.every((request) => request.sortOrder === null)).toBe(
      true,
    )

    await page.getByRole("button", { name: "Block" }).click()
    await expect(page.getByRole("columnheader", { name: "Block" })).toHaveCount(
      0,
    )
  })

  test("jumpstats leaderboard row opens details dialog and preserves row link navigation", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.clear()
      let copiedText = ""
      let lastOpenedUrl = ""
      Object.defineProperty(window, "__jumpstatCopiedText", {
        configurable: true,
        get: () => copiedText,
        set: (value: string) => {
          copiedText = value
        },
      })
      Object.defineProperty(window, "__lastOpenedUrl", {
        configurable: true,
        get: () => lastOpenedUrl,
        set: (value: string) => {
          lastOpenedUrl = value
        },
      })
      Object.defineProperty(window, "open", {
        configurable: true,
        value: (url?: string | URL) => {
          lastOpenedUrl =
            typeof url === "string" ? url : (url?.toString?.() ?? "")
          return null
        },
      })
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: async (text: string) => {
            copiedText = text
          },
        },
      })
    })
    await page.route("**/v1/leaderboards/jumpstats*", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          data: [
            {
              rank: 1,
              id: "11111111-1111-4111-8111-111111111111",
              player: buildPlayerRef("76561198000000003", "Gamma"),
              server_group_id: "22222222-2222-4222-8222-222222222222",
              server_group: {
                id: "22222222-2222-4222-8222-222222222222",
                name: "Jumpstats Group",
              },
              mode: "KZT",
              type: "LJ",
              distance: 281.1234,
              block: 280,
              strafes: 8,
              sync_percent: 90,
              pre_speed: 275.22,
              max_speed: 366.78,
              jumped_at: "2099-01-01T00:00:00Z",
            },
          ],
        }),
      })
    })
    await page.route(
      /\/v1\/jumpstats\/11111111-1111-4111-8111-111111111111$/,
      async (route) => {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            id: "11111111-1111-4111-8111-111111111111",
            player: buildPlayerRef("76561198000000003", "Gamma"),
            server_group_id: "22222222-2222-4222-8222-222222222222",
            server_group: {
              id: "22222222-2222-4222-8222-222222222222",
              name: "Jumpstats Group",
            },
            mode: "KZT",
            type: "LJ",
            distance: 281.1234,
            block: 280,
            strafes: 8,
            sync_percent: 90,
            pre_speed: 275.22,
            max_speed: 366.78,
            w_count: 1,
            overlap_count: 0,
            dead_air_count: 0,
            width: 18.5,
            height: 56.1,
            airtime_percent: 100,
            offset: 0,
            crouched_ticks: 0,
            edge: null,
            deviation: 3.25,
            jumped_at: "2099-01-01T00:00:00Z",
            created_at: "2099-01-01T00:00:00Z",
            updated_at: "2099-01-01T00:00:00Z",
            strafe_stats: [
              {
                index: 1,
                sync_percent: 90,
                gain: 10,
                loss: 0,
                airtime_percent: 50,
                width: 12,
                overlap_count: 0,
                dead_air_count: 0,
              },
            ],
          }),
        })
      },
    )
    await page.route(
      /\/v1\/jumpstats\/11111111-1111-4111-8111-111111111111\/visualization$/,
      async (route) => {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            version: 1,
            jump_direction: "FORWARDS",
            deviation_angle: 12.5,
            bounds: {
              min_x: -1,
              max_x: 1,
              min_y: 0,
              max_y: 3,
            },
            samples: [
              {
                index: 0,
                x: 0,
                y: 0,
                yaw_delta: 0,
                mouse_direction: "NONE",
                a_pressed: false,
                d_pressed: false,
                strafe_type: "NONE",
              },
              {
                index: 1,
                x: 0.2,
                y: 2.5,
                yaw_delta: 8,
                mouse_direction: "RIGHT",
                a_pressed: false,
                d_pressed: true,
                strafe_type: "RIGHT",
              },
            ],
          }),
        })
      },
    )

    await page.goto("/leaderboards/jumpstats")

    const detailResponsePromise = page.waitForResponse(
      /\/v1\/jumpstats\/11111111-1111-4111-8111-111111111111$/,
    )
    const visualizationResponsePromise = page.waitForResponse(
      /\/v1\/jumpstats\/11111111-1111-4111-8111-111111111111\/visualization$/,
    )
    await page.locator("tbody tr").first().click()
    await detailResponsePromise
    await visualizationResponsePromise
    await expect(page.getByRole("dialog")).toBeVisible()
    await expect(page.getByRole("dialog")).toContainText(
      "Gamma jumped 281.1234 units with a Long Jump",
    )
    await expect(
      page.getByRole("img", { name: "Route visualization" }),
    ).toBeVisible()
    await expect(page.getByRole("dialog")).toContainText(
      "Deviation angle: 12.50°",
    )
    await expect(
      page.getByRole("button", { name: "Copy details" }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Play this jump replay" }),
    ).toBeVisible()
    await page.getByRole("button", { name: "Play this jump replay" }).click()
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            (window as Window & { __lastOpenedUrl?: string }).__lastOpenedUrl ??
            "",
        ),
      )
      .toBe(
        "http://localhost:5180/?jump_id=11111111-1111-4111-8111-111111111111",
      )
    await page.getByRole("button", { name: "Copy details" }).click()
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            (window as Window & { __jumpstatCopiedText?: string })
              .__jumpstatCopiedText ?? "",
        ),
      )
      .toContain("Gamma jumped 281.1234 units with a Long Jump")
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Close" })
      .click()
    await expect(page.getByRole("dialog")).not.toBeVisible()
    await expect(
      page.getByRole("tab", { name: "Long Jump", exact: true }),
    ).toHaveAttribute("data-state", "active")

    await page.getByRole("link", { name: "Gamma" }).click()
    await expect(page).toHaveURL(/\/profile\/76561198000000003/)
  })

  test("jumpstats details dialog shows visualization error without hiding detail", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.clear()
    })
    await page.route("**/v1/leaderboards/jumpstats*", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          data: [
            {
              rank: 1,
              id: "33333333-3333-4333-8333-333333333333",
              player: buildPlayerRef("76561198000000004", "Delta"),
              server_group_id: "44444444-4444-4444-8444-444444444444",
              server_group: {
                id: "44444444-4444-4444-8444-444444444444",
                name: "Jumpstats Group",
              },
              mode: "KZT",
              type: "LJ",
              distance: 280.5,
              block: 260,
              strafes: 7,
              sync_percent: 88,
              pre_speed: 274.11,
              max_speed: 365.41,
              jumped_at: "2099-01-01T00:00:00Z",
            },
          ],
        }),
      })
    })
    await page.route(
      /\/v1\/jumpstats\/33333333-3333-4333-8333-333333333333$/,
      async (route) => {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            id: "33333333-3333-4333-8333-333333333333",
            player: buildPlayerRef("76561198000000004", "Delta"),
            server_group_id: "44444444-4444-4444-8444-444444444444",
            server_group: {
              id: "44444444-4444-4444-8444-444444444444",
              name: "Jumpstats Group",
            },
            mode: "KZT",
            type: "LJ",
            distance: 280.5,
            block: 260,
            strafes: 7,
            sync_percent: 88,
            pre_speed: 274.11,
            max_speed: 365.41,
            w_count: 1,
            overlap_count: 0,
            dead_air_count: 0,
            width: 18.5,
            height: 56.1,
            airtime_percent: 100,
            offset: 0,
            crouched_ticks: 0,
            edge: null,
            deviation: 3.25,
            jumped_at: "2099-01-01T00:00:00Z",
            created_at: "2099-01-01T00:00:00Z",
            updated_at: "2099-01-01T00:00:00Z",
            strafe_stats: [
              {
                index: 1,
                sync_percent: 88,
                gain: 12,
                loss: 0,
                airtime_percent: 50,
                width: 14,
                overlap_count: 0,
                dead_air_count: 0,
              },
            ],
          }),
        })
      },
    )
    await page.route(
      /\/v1\/jumpstats\/33333333-3333-4333-8333-333333333333\/visualization$/,
      async (route) => {
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({
            detail: "33333333-3333-4333-8333-333333333333.replay",
          }),
        })
      },
    )

    await page.goto("/leaderboards/jumpstats")

    const detailResponsePromise = page.waitForResponse(
      /\/v1\/jumpstats\/33333333-3333-4333-8333-333333333333$/,
    )
    const visualizationResponsePromise = page.waitForResponse(
      /\/v1\/jumpstats\/33333333-3333-4333-8333-333333333333\/visualization$/,
    )
    await page.locator("tbody tr").first().click()
    await detailResponsePromise
    await visualizationResponsePromise
    await expect(page.getByRole("dialog")).toBeVisible()
    await expect(page.getByRole("dialog")).toContainText(
      "Unable to load jump route",
    )
    await expect(
      page.getByText("Strafe breakdown", { exact: true }),
    ).toBeVisible()
  })
})
