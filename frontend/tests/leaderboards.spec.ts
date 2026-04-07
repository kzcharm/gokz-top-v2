import { expect, test } from "@playwright/test"

test.describe("Leaderboards page", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("renders leaderboard empty state", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.clear()
    })
    await page.route("**/v1/leaderboards/players*", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          data: [],
          count: 0,
        }),
      })
    })

    await page.goto("/leaderboards")

    await expect(
      page.getByRole("heading", { name: "Leaderboards" }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Find Me", exact: true }),
    ).toBeDisabled()
    await expect(
      page.getByRole("button", { name: "Select record scope" }),
    ).toContainText("OVR")
    await expect(page.getByText("No results found.")).toBeVisible()
  })

  test("switching scope refetches leaderboard data", async ({ page }) => {
    const requestedScopes: string[] = []

    await page.addInitScript(() => {
      localStorage.clear()
    })
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
              player: {
                steamid64: "76561198000000001",
                name: `Scope ${scope}`,
                alias: null,
                custom_id: null,
                avatar_hash: null,
                country: null,
                created_at: null,
                last_played_at: null,
                updated_at: null,
                profile_views: 0,
              },
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

    await page.route("**/v1/players/search*", async (route) => {
      const url = new URL(route.request().url())
      const query = url.searchParams.get("q") || ""

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count:
            query.toLowerCase() === "beta" || query.toLowerCase() === "gamma"
              ? 1
              : 0,
          data: (() => {
            if (query.toLowerCase() === "beta") {
              return [
                {
                  steamid64: "76561198000000002",
                  name: "Beta",
                  alias: null,
                  custom_id: "beta",
                  avatar_hash: null,
                  country: null,
                  created_at: null,
                  last_played_at: null,
                  updated_at: null,
                  profile_views: 0,
                },
              ]
            }

            if (query.toLowerCase() === "gamma") {
              return [
                {
                  steamid64: "76561198000000003",
                  name: "Gamma",
                  alias: null,
                  custom_id: "gamma",
                  avatar_hash: null,
                  country: null,
                  created_at: null,
                  last_played_at: null,
                  updated_at: null,
                  profile_views: 0,
                },
              ]
            }

            return []
          })(),
        }),
      })
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
                player: {
                  steamid64: "76561198000000002",
                  name: "Beta",
                  alias: null,
                  custom_id: "beta",
                  avatar_hash: null,
                  country: null,
                  created_at: null,
                  last_played_at: null,
                  updated_at: null,
                  profile_views: 0,
                },
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
              player: {
                steamid64: `76561198000000${(offset + index + 1).toString().padStart(3, "0")}`,
                name: `Player ${offset + index + 1}`,
                alias: null,
                custom_id: null,
                avatar_hash: null,
                country: null,
                created_at: null,
                last_played_at: null,
                updated_at: null,
                profile_views: 0,
              },
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

    await page.route("**/v1/users/me", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          steamid64: "76561198000000042",
          is_superuser: false,
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
              player: {
                steamid64: `76561198000000${(offset + index + 1).toString().padStart(3, "0")}`,
                name: `Player ${offset + index + 1}`,
                alias: null,
                custom_id: null,
                avatar_hash: null,
                country: null,
                created_at: null,
                last_played_at: null,
                updated_at: null,
                profile_views: 0,
              },
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
})
