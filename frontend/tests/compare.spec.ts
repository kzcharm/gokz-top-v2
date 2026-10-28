import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const player1 = "76561198000000001"
const player2 = "76561198000000002"
let hasWorldRecords = false

test.beforeEach(async ({ page }) => {
  hasWorldRecords = false
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("compare-test-initialized")) {
      localStorage.clear()
      sessionStorage.setItem("compare-test-initialized", "true")
    }
  })
  await page.route("**/v1/maps?*", (route) =>
    route.fulfill({
      json: Array.from({ length: 12 }, (_, index) => ({
        id: index + 1,
        name: `kz_map_${index + 1}`,
        tiers: { OVR: 1, KZT: 1, SKZ: 1, VNL: 1 },
      })),
    }),
  )
  await page.route("**/v1/maps/wrs?*", (route) =>
    route.fulfill({ json: [{ map_id: 1 }] }),
  )
  await page.route("**/v1/leaderboards/players/*", (route) =>
    route.fulfill({
      json: {
        skill_ratings: Object.fromEntries(
          ["boxtech", "strafe", "bhop", "climb", "ladder", "slide"].map(
            (skill) => [skill, { rating: 5, raw_rating: 1 }],
          ),
        ),
      },
    }),
  )
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
      wrs_nub: hasWorldRecords && steamid64 === player1 ? 1 : 0,
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
        nub_runs: Array.from({ length: 12 }, (_, index) => {
          const record = (points: number, time: number) => ({
            uuid: `run-${index}-${points}`,
            map_id: index + 1,
            map_name: `kz_map_${index + 1}`,
            map_tier: 1,
            mode: "KZT",
            teleports: 2,
            points,
            time,
            server_name: "Test Server",
            created_on: `2026-10-${String(points === 800 ? 20 - index : index + 1).padStart(2, "0")}T12:00:00Z`,
          })
          return {
            map_id: index + 1,
            map_name: `kz_map_${index + 1}`,
            map_tier: 1,
            player1: record(1000 - index * 10, 100 + index),
            player2:
              index === 11
                ? null
                : record(
                    800,
                    index === 0 ? 100 : index === 1 ? 90 : 120 + index,
                  ),
            time_delta: index === 11 ? null : 20,
            points_delta: index === 11 ? null : -200 + index * 10,
          }
        }),
        pro_runs: [],
      }),
    })
  })
})

test("comparison ratings floor decimals without changing unavailable values", async ({
  page,
}) => {
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

test("plain SteamID64 URLs preserve every digit and legacy URLs normalize", async ({
  page,
}) => {
  const seen: string[] = []
  page.on("request", (request) => {
    if (request.url().includes("/players/compare?")) seen.push(request.url())
  })
  await page.goto(`/compare?player1=${player1}&player2=${player2}`)
  await expect(
    page.getByRole("heading", { name: "Skills", exact: true }),
  ).toBeVisible()
  expect(new URL(seen[0]).searchParams.get("player1")).toBe(player1)
  expect(new URL(seen[0]).searchParams.get("player2")).toBe(player2)
  await expect(page.getByTestId("compare-completion")).toContainText("12 / 12")
  await expect(page.getByTestId("compare-completion")).toContainText("11 / 12")
  await page.getByRole("button", { name: "Swap players" }).click()
  await expect(page).toHaveURL(
    new RegExp(`player1=${player2}&player2=${player1}$`),
  )
  await page.goBack()
  await expect(page).toHaveURL(
    new RegExp(`player1=${player1}&player2=${player2}$`),
  )
  await page.goto(`/compare?player1=%22${player1}%22&player2=%22${player2}%22`)
  await expect(page).toHaveURL(
    new RegExp(`player1=${player1}&player2=${player2}$`),
  )
  await page.getByRole("button", { name: "Swap players" }).click()
  await expect(page).toHaveURL(
    new RegExp(`player1=${player2}&player2=${player1}$`),
  )
})

test("runs sort, filter by player, and paginate the filtered collection", async ({
  page,
}) => {
  await page.goto(`/compare?player1=${player1}&player2=${player2}`)
  const rows = page.locator("tbody tr")
  await expect(rows).toHaveCount(11)
  await expect(page.getByTestId("compare-win-count-player1")).toHaveText("9")
  await expect(page.getByTestId("compare-win-count-player2")).toHaveText("1")
  await expect(rows.first()).toContainText("kz_map_11")
  await expect(rows.first()).toContainText("2026-10-11")
  await expect(rows.first()).toContainText("2026-10-10")
  await expect(rows.first().getByText("800", { exact: true })).toBeVisible()
  await expect(
    page
      .getByRole("button", { name: "Sort by Tier", exact: true })
      .locator("svg"),
  ).toHaveCount(0)
  await expect(
    page.getByText("Shared 0–11 scale for comparing players.", { exact: true }),
  ).toHaveCount(0)
  await expect(rows.first().locator("[data-player] img")).toHaveCount(0)
  await expect(
    page.getByRole("columnheader", { name: "Time delta" }),
  ).toHaveCount(0)
  await expect(
    page.getByRole("columnheader", { name: "Points delta" }),
  ).toHaveCount(0)
  await expect(
    rows
      .first()
      .locator('[data-player="player2"]')
      .getByTestId("compare-time-delta"),
  ).toHaveText("(1.18x)")
  await expect(
    rows
      .first()
      .locator('[data-player="player1"]')
      .getByTestId("compare-points-delta"),
  ).toHaveText("(+100)")
  await page.getByRole("button", { name: "Ratio", exact: true }).click()
  await expect(rows.first().getByTestId("compare-time-delta")).toHaveText(
    "(1.18x)",
  )
  await expect(rows.first().getByTestId("compare-points-delta")).toHaveText(
    "(+100)",
  )
  await page.getByRole("button", { name: "Difference", exact: true }).click()
  await expect(rows.first().getByTestId("compare-time-delta")).toHaveText(
    "(+0:20.000)",
  )
  await page.reload()
  await expect(
    page.getByRole("button", { name: "Difference", exact: true }),
  ).toHaveAttribute("aria-pressed", "true")
  await expect(rows.first().getByTestId("compare-time-delta")).toHaveText(
    "(+0:20.000)",
  )
  await page.getByRole("button", { name: "Ratio", exact: true }).click()
  await page.reload()
  await expect(
    page.getByRole("button", { name: "Ratio", exact: true }),
  ).toHaveAttribute("aria-pressed", "true")
  await expect(rows.first().getByTestId("compare-points-delta")).toHaveText(
    "(+100)",
  )
  const dateSort = page.getByRole("button", {
    name: "Sort by Date",
    exact: true,
  })
  // Default P1 descending -> P2 ascending -> P2 descending -> P1 ascending -> P1 descending.
  for (const [indicator, map] of [
    ["P2", "kz_map_11"],
    ["P2", "kz_map_1"],
    ["P1", "kz_map_1"],
    ["P1", "kz_map_11"],
  ]) {
    await dateSort.click()
    await expect(dateSort).toContainText(indicator)
    await expect(rows.first()).toContainText(map)
  }
  await expect(rows.first().locator('[data-player="player1"]')).toHaveCount(6)
  await expect(rows.first().locator('[data-player="player2"]')).toHaveCount(6)
  await page.getByRole("button", { name: "Sort by Map", exact: true }).click()
  await expect(rows.first()).toContainText("kz_map_1")
  await page.getByRole("button", { name: "Sort by Map", exact: true }).click()
  await expect(rows.first()).toContainText("kz_map_11")
  await page.getByRole("textbox", { name: "Search maps" }).fill("map_2")
  await expect(rows).toHaveCount(1)
  await expect(page.getByTestId("compare-win-count-player1")).toHaveText("0")
  await expect(page.getByTestId("compare-win-count-player2")).toHaveText("1")
  await expect(rows.first()).toContainText("kz_map_2")
  await page.getByRole("button", { name: "Clear Filters" }).click()
  await page.locator("summary").filter({ hasText: "Filters" }).click()
  await page
    .getByRole("spinbutton", { name: "Points min", exact: true })
    .fill("950")
  await expect(rows).toHaveCount(6)
  await page.getByRole("combobox", { name: "Apply run filters to" }).click()
  await page.getByRole("option", { name: "Both players" }).click()
  await expect(
    page.getByText("No main-stage PBs match this view."),
  ).toBeVisible()
  await page.getByRole("button", { name: "Clear Filters" }).click()
  await page.getByRole("switch", { name: "Only maps finished by both" }).click()
  await expect(rows).toHaveCount(12)
  await page.getByRole("combobox").filter({ hasText: "50" }).click()
  await page.getByRole("option", { name: "10", exact: true }).click()
  await expect(rows).toHaveCount(10)
  await expect(page.getByTestId("compare-win-count-player1")).toHaveText("9")
  await expect(page.getByTestId("compare-win-count-player2")).toHaveText("1")
  await page
    .getByRole("button", { name: "Go to next page", exact: true })
    .click()
  await expect(rows).toHaveCount(2)
  await page.getByRole("textbox", { name: "Search maps" }).fill("map_2")
  await expect(rows).toHaveCount(1)
  await page.screenshot({
    path: "../.temp/compare/desktop.png",
    fullPage: true,
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(
    page.getByRole("heading", { name: "Runs", exact: true }),
  ).toBeVisible()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  await page.screenshot({ path: "../.temp/compare/mobile.png", fullPage: true })
})

test("completion toggles one mirrored profile-style chart and highlights a player", async ({
  page,
}) => {
  await page.goto(`/compare?player1=${player1}&player2=${player2}`)
  const chart = page.getByTestId("compare-completion")
  await expect(chart).toHaveCount(1)
  await expect(chart.getByRole("progressbar")).toHaveCount(16)
  await expect(page.getByText("NUB WRs", { exact: true })).toHaveCount(0)
  await expect(page.getByText("PRO WRs", { exact: true })).toHaveCount(0)
  const left = page.getByTestId("compare-track-player1-1")
  const right = page.getByTestId("compare-track-player2-1")
  await expect(left).toHaveCSS("height", "20px")
  const tierRow = left.locator("..")
  await expect(tierRow).toHaveCSS("height", "20px")
  await expect(tierRow.locator("[data-completion-tier-label]")).toHaveText(
    "T1 (avg 945)",
  )
  await expect(
    chart.getByRole("img", { name: "gold trophy", exact: true }).first(),
  ).toHaveCSS("height", "28px")
  await expect(left.locator("div")).toHaveCSS(
    "background-color",
    "rgb(71, 170, 103)",
  )
  await expect(left.locator("div")).toHaveClass(/ml-auto/)
  await expect(right.locator("div")).not.toHaveClass(/ml-auto/)
  const identity = page.getByTestId("compare-identity-player1")
  await expect(identity.locator('[data-slot="avatar"]')).toHaveCSS(
    "width",
    "128px",
  )
  await expect(identity.locator('[data-testid^="rating-icon-"]')).toHaveCount(0)
  await identity.hover()
  await expect(
    chart.locator('[data-compare-player="player2"]').first(),
  ).toHaveCSS("opacity", "0.3")
  await expect(
    page.locator('[data-compare-metric="player2"]').first(),
  ).toHaveCSS("opacity", "0.3")
  await page.getByRole("heading", { name: "Runs", exact: true }).hover()
  await expect(
    chart.locator('[data-compare-player="player2"]').first(),
  ).toHaveCSS("opacity", "1")
  await identity.getByRole("link").focus()
  await expect(
    page.locator('[data-compare-metric="player2"]').first(),
  ).toHaveCSS("opacity", "0.3")
  await page.getByRole("switch", { name: "Show PRO completion" }).click()
  await expect(
    chart.getByRole("heading", { name: /^PRO completion$/i }),
  ).toBeVisible()
  await expect(
    chart.getByRole("progressbar", { name: "Alpha: PRO T1", exact: true }),
  ).toHaveAttribute("aria-valuenow", "0")
  await expect(chart.getByRole("progressbar", { name: /NUB/ })).toHaveCount(0)
  await page.getByRole("switch", { name: "Show PRO completion" }).click()
  await expect(
    chart.getByRole("progressbar", { name: "Alpha: NUB T1", exact: true }),
  ).toHaveAttribute("aria-valuenow", "12")
  await page.screenshot({
    path: "../.temp/compare/mirrored-desktop.png",
    fullPage: true,
  })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await page.screenshot({
    path: "../.temp/compare/mirrored-mobile.png",
    fullPage: true,
  })
})

test("WR metrics remain visible if either player has a WR", async ({
  page,
}) => {
  hasWorldRecords = true
  await page.goto(`/compare?player1=${player1}&player2=${player2}`)
  await expect(page.getByText("NUB WRs", { exact: true })).toBeVisible()
  await expect(page.getByText("PRO WRs", { exact: true })).toBeVisible()
})

test("stacked records preview", async ({ page }) => {
  await page.goto(`/compare?player1=${player1}&player2=${player2}`)
  await expect(page.locator("tbody tr")).toHaveCount(11)
  await page
    .locator("#compare-runs")
    .screenshot({ path: "../.temp/compare/stacked-desktop.png" })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
})
