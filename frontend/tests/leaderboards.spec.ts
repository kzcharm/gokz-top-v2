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
    await expect(page.getByText("Active scope: OVR")).toBeVisible()
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

    await expect(page.getByText("Active scope: KZT")).toBeVisible()
    await expect(page.getByText("Scope KZT")).toBeVisible()
    expect(requestedScopes).toContain("OVR")
    expect(requestedScopes).toContain("KZT")
  })
})
