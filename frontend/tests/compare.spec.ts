import { expect, test } from "@playwright/test"

const player1 = "76561198000000001"
const player2 = "76561198000000002"

test("comparison ratings floor decimals without changing unavailable values", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.clear()
  })
  await page.route("**/v1/graphql", async (route) => {
    const request = route.request().postDataJSON() as {
      query?: string
      variables?: { identifier?: string; q?: string }
    }
    const isSearch = request.query?.includes("searchPlayers") ?? false
    const identifier = isSearch
      ? request.variables?.q === "Beta"
        ? player2
        : player1
      : (request.variables?.identifier ?? player1)
    const displayName = identifier === player1 ? "Alpha" : "Beta"
    const player = {
      steamid64: identifier,
      displayName,
      name: displayName,
      alias: null,
      customId: null,
      avatarHash: null,
      country: null,
      primaryScope: "OVR",
      rating: 0,
      roles: null,
      lastPlayedAt: null,
      createdAt: null,
      updatedAt: null,
      profileViews: 0,
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: isSearch
          ? { searchPlayers: { count: 1, data: [player] } }
          : { player },
      }),
    })
  })
  await page.route("**/v1/players/compare*", async (route) => {
    const summary = (
      steamid64: string,
      displayName: string,
      rating: number,
    ) => ({
      scope: "OVR",
      rank: 1,
      global_rank: 1,
      rank_regional: null,
      region: null,
      player: { steamid64, display_name: displayName },
      rating,
      rating_easy: 2,
      rating_hard: null,
      points: 1000,
      wrs_nub: 0,
      wrs_pro: 0,
      records_900_plus: 0,
      records_800_plus: 0,
      unique_map_finishes: 10,
    })
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        scope: "OVR",
        player1: summary(player1, "Alpha", 4.409),
        player2: summary(player2, "Beta", 4.4),
        progression: Array.from({ length: 8 }, (_, index) => ({
          tier: index + 1,
          total_maps: 0,
          player1_finished: 0,
          player2_finished: 0,
        })),
        nub_runs: [],
        pro_runs: [],
      }),
    })
  })

  await page.goto("/compare")
  await page.getByRole("textbox", { name: "Search player 1" }).fill("Alpha")
  await page
    .locator("button")
    .filter({ has: page.getByText("Alpha", { exact: true }) })
    .click()
  await page.getByRole("textbox", { name: "Search player 2" }).fill("Beta")
  await page
    .locator("button")
    .filter({ has: page.getByText("Beta", { exact: true }) })
    .click()

  const ratingRow = page.getByText("Rating", { exact: true }).locator("..")
  await expect(ratingRow.getByText("4.40", { exact: true })).toHaveCount(2)
  const hardRatingRow = page
    .getByText("Rating H", { exact: true })
    .locator("..")
  await expect(hardRatingRow).toContainText("-Rating H-")
})
