import { expect, type Page, test, type WebSocketRoute } from "@playwright/test"
import {
  formatWrGap,
  getWrGap,
  wrGapScaleToRatio,
} from "../src/components/Records/wr-gap"

test.use({ storageState: { cookies: [], origins: [] } })

test("WR Gap uses ratios and rejects invalid inputs", () => {
  expect(getWrGap(125, 100)).toBe(1.25)
  expect(getWrGap(200, 100)).toBe(2)
  expect(getWrGap(500, 100)).toBe(5)
  expect(getWrGap(100, 100)).toBe(1)
  for (const [time, wr] of [
    [90, 100],
    [0, 100],
    [100, 0],
    [100, Number.NaN],
    [Number.POSITIVE_INFINITY, 100],
  ]) {
    expect(getWrGap(time, wr)).toBeNull()
  }
})

const steamid64 = "76561198000000001"
const player = {
  steamid64,
  name: "Map Picker",
  alias: null,
  custom_id: null,
  country: "DE",
  avatar_hash: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  last_played_at: null,
}
const maps = Array.from({ length: 30 }, (_, index) => ({
  id: index + 1,
  name: `kz_pick_${String(index).padStart(2, "0")}`,
  filesize: 100,
  validated: true,
  tiers: { OVR: 3, KZT: 3, SKZ: 3, VNL: 3 },
  created_on: "2026-01-01T00:00:00Z",
  updated_on: "2026-02-01T00:00:00Z",
  approved_by_steamid64: steamid64,
  workshop_id: null,
  synced_at: "2026-02-01T00:00:00Z",
  authors: [],
  no_steamid_names: [],
  bonus_count: index % 4,
  review_summary: null,
}))

function pb(index: number, time: number, teleports: number) {
  return {
    uuid: `019d0000-0000-7000-8000-${String(index + 1).padStart(12, "0")}`,
    id: index,
    player: { steamid64, display_name: player.name },
    map_id: maps[index].id,
    map_name: maps[index].name,
    map_tier: 3,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time,
    teleports,
    points: 1000 - time + 0.123456,
    raw_rating_contribution: time,
    server_id: 1,
    server_name: "Test",
    created_on: `2026-01-${String(index + 1).padStart(2, "0")}T00:00:00Z`,
    updated_on: "2026-02-01T00:00:00Z",
    updated_by: steamid64,
    is_valid: true,
    is_replay_available: false,
    replay_id: null,
  }
}

async function install(
  page: Page,
  { guest = false, failPb = false, wrBased = true } = {},
) {
  const requests: string[] = []
  await page.addInitScript(
    ({ guest }) => {
      localStorage.setItem("gokz-app-scope", "OVR")
      localStorage.setItem("gokz-datetime-format", "iso")
      if (!guest) localStorage.setItem("access_token", "mock-token")
    },
    { guest },
  )
  await page.routeWebSocket(/\/v1\/ws\//, () => {})
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path === "/v1/users/me")
      return route.fulfill({
        json: guest ? null : { steamid64, roles: [], player },
      })
    if (path === "/v1/me/settings")
      return route.fulfill({ json: { use_wr_based_pro_completion: wrBased } })
    if (path === "/v1/records/pb") {
      requests.push(
        `${url.searchParams.get("scope")}:${url.searchParams.get("type")}:${url.searchParams.get("stage")}`,
      )
      return route.fulfill(
        failPb
          ? { status: 500, json: { detail: "failed" } }
          : {
              json:
                url.searchParams.get("scope") === "SKZ"
                  ? []
                  : url.searchParams.get("type") === "PRO"
                    ? [pb(1, 25, 0)]
                    : [pb(0, 30, 4), pb(1, 20, 2), pb(27, 12, 1)],
            },
      )
    }
    if (path === "/v1/maps") return route.fulfill({ json: maps })
    if (path === "/v1/maps/wrs")
      return route.fulfill({
        json: maps
          .filter(
            (_, index) => url.searchParams.get("type") !== "PRO" || index < 3,
          )
          .map((map) => ({
            map_id: map.id,
            scope: url.searchParams.get("scope"),
            type: url.searchParams.get("type"),
            time: 10,
            teleports: 0,
            mode_id: 200,
            player: { steamid64, display_name: player.name },
            updated_at: "2026-02-01T00:00:00Z",
          })),
      })
    if (path === "/v1/leaderboards/maps")
      return route.fulfill({
        json: {
          count: 4,
          data: maps.slice(0, 4).map((map, index) => ({
            map: { id: map.id, name: map.name },
            total_playtime: 1000,
            average_playtime_per_player: 100,
            unique_nub_finishes: 10,
            unique_pro_finishes: 5,
            pro_nub_ratio: 0.5,
            total_finishes: 20,
            median_first_completion_time: [12.5, 20, 50, 10][index],
          })),
        },
      })
    if (path === "/v1/graphql") {
      const body = route.request().postDataJSON()
      return route.fulfill({
        json: {
          data: body.query.includes("MapImages")
            ? {
                mapImages: (body.variables.inputs ?? []).map(
                  (input: object) => ({ ...input, previewUrl: null }),
                ),
              }
            : { players: (body.variables.steamid64s ?? []).map(() => null) },
        },
      })
    }
    if (path === `/v1/players/${steamid64}`)
      return route.fulfill({ json: player })
    if (path.endsWith("/setup"))
      return route.fulfill({
        json: { hardware: [], game_settings: {}, operating_system: null },
      })
    if (path.endsWith("/views"))
      return route.fulfill({ json: { profile_views: 0 } })
    if (path.endsWith("/likes"))
      return route.fulfill({ json: { player_likes: 0, created: false } })
    if (path.endsWith("/follow-summary"))
      return route.fulfill({
        json: {
          follower_count: 0,
          following_count: 0,
          viewer_is_self: true,
          viewer_is_following: false,
        },
      })
    if (path.endsWith("/stats"))
      return route.fulfill({
        json: {
          steamid64,
          daily_activity: null,
          playtime: { updated_at: null, total_seconds: 0 },
        },
      })
    if (path.startsWith("/v1/leaderboards/players/"))
      return route.fulfill({
        json: { rank: 1, rank_regional: 1, region: "EU", rating: 5 },
      })
    return route.fulfill({ json: { data: [], count: 0, unread_count: 0 } })
  })
  return requests
}

async function completion(page: Page, label: string) {
  const group = page.getByRole("button", { name: "My Runs", exact: true })
  if ((await group.getAttribute("aria-pressed")) !== "true") await group.click()
  for (const name of ["Finished", "Unfinished"]) {
    const button = page.getByRole("button", { name, exact: true })
    const pressed = (await button.getAttribute("aria-pressed")) === "true"
    if ((label === name) !== pressed) await button.click()
  }
}

async function order(page: Page, names: string[]) {
  await expect(page.locator('[data-testid^="map-card-"]')).toHaveCount(
    names.length,
  )
  await expect(page.locator('[data-testid^="map-card-"] h2 a')).toHaveText(
    names,
  )
}

test("one PB type drives overlay, completion, and full-catalog sorting", async ({
  page,
}) => {
  const requests = await install(page)
  await page.goto("/maps")
  await expect(page.getByTestId("map-pb-1")).toHaveText("PB: 0:30.000")
  await expect(page.getByLabel("Filter maps by tier")).toContainText("Tier")
  await expect(
    page.getByRole("button", { name: "Use PRO personal bests" }),
  ).toHaveText("NUB")
  await expect(page.getByTestId("map-pb-3")).toHaveText("Unfinished")
  await page.getByRole("button", { name: "My Runs", exact: true }).click()
  await page.getByRole("button", { name: "PB Time", exact: true }).click()
  await expect(
    page.locator('[data-testid^="map-card-"]').first(),
  ).toHaveAttribute("data-testid", "map-card-kz_pick_27")
  await completion(page, "Finished")
  await order(page, ["kz_pick_27", "kz_pick_01", "kz_pick_00"])
  await page.getByRole("button", { name: "Use PRO personal bests" }).click()
  await order(page, ["kz_pick_01"])
  await expect(page.getByTestId("map-pb-2")).toHaveText("PB: 0:25.000")
  await completion(page, "Unfinished")
  await order(page, ["kz_pick_00", "kz_pick_02"])
  expect(requests).toEqual(["OVR:NUB:0", "OVR:PRO:0"])
  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "SKZ" }).click()
  await expect(page.getByTestId("map-pb-1")).toHaveText("Unfinished")
  expect(requests).toContain("SKZ:PRO:0")
})

for (const first of ["maps", "profile"] as const) {
  test(`PB cache is shared when ${first} is opened first`, async ({ page }) => {
    const requests = await install(page)
    await page.goto(first === "maps" ? "/maps" : `/profile/${steamid64}/runs`)
    if (first === "maps") {
      await expect(page.getByTestId("map-pb-1")).toContainText("0:30.000")
      await page.locator(`a[href="/profile/${steamid64}"]`).first().click()
      await page.getByRole("tab", { name: "Runs", exact: true }).click()
    } else {
      await expect(page.getByText(maps[0].name).first()).toBeVisible()
      await page
        .getByRole("link", { name: "Maps", exact: true })
        .first()
        .click()
    }
    await expect.poll(() => requests.length).toBe(2)
    expect(requests.sort()).toEqual(["OVR:NUB:0", "OVR:PRO:0"])
    await page.reload()
    await expect.poll(() => requests.length).toBe(4)
  })
}

test("live Runs updates are reused by the catalog", async ({ page }) => {
  const requests = await install(page)
  let socket: WebSocketRoute | undefined
  let updated = false
  await page.routeWebSocket(/\/v1\/ws\/records\/recent/, (route) => {
    socket = route
  })
  await page.route("**/v1/records/pb?**", async (route) => {
    if (!updated) return route.fallback()
    const url = new URL(route.request().url())
    requests.push(
      `${url.searchParams.get("scope")}:${url.searchParams.get("type")}:${url.searchParams.get("stage")}`,
    )
    await route.fulfill({
      json:
        url.searchParams.get("type") === "NUB"
          ? [pb(0, 15, 2)]
          : [pb(1, 25, 0)],
    })
  })
  await page.goto(`/profile/${steamid64}/runs`)
  await expect.poll(() => Boolean(socket)).toBe(true)
  await expect(page.getByText("0:30.000").first()).toBeVisible()
  expect(requests).toHaveLength(2)
  updated = true
  socket?.send(
    JSON.stringify({
      type: "record.upserted",
      record: { player: { steamid64 } },
    }),
  )
  await expect(page.getByText("0:15.000").first()).toBeVisible()
  await expect.poll(() => requests.length).toBe(4)
  await page.getByRole("link", { name: "Maps", exact: true }).first().click()
  await expect(page.getByTestId("map-pb-1")).toHaveText("PB: 0:15.000")
  expect(requests).toHaveLength(4)
})

test("public metrics explain values, sort gaps, and persist card options", async ({
  page,
}) => {
  const requests = await install(page, { guest: true })
  await page.goto("/maps")
  await expect(
    page.getByRole("button", { name: "Use PRO personal bests" }),
  ).toHaveCount(0)
  await page.getByRole("button", { name: "Metrics", exact: true }).click()
  await expect(
    page.getByRole("button", { name: "Metrics", exact: true }).locator("svg"),
  ).toHaveCount(0)
  const metricButtons = page
    .getByRole("group", { name: "Metrics", exact: true })
    .getByRole("button")
  await expect(metricButtons.nth(0)).toHaveText("NUB Finishers")
  await expect(metricButtons.nth(0)).toHaveAttribute("aria-pressed", "true")
  await expect(metricButtons.nth(1)).toHaveText("PRO Finishers")
  for (const [label, explanation] of [
    ["Playtime", "Sum of valid main-course"],
    ["Avg Playtime", "Average cumulative"],
    ["NUB Finishers", "including PRO finishes"],
    ["PRO Finishers", "using zero teleports"],
    ["PRO Ratio", "Percentage of main-course"],
    ["Total Runs", "including repeat finishes"],
    ["1st Med", "Median of each player"],
    ["1st Med WR Gap", "median PB / WR"],
    ["Bonus", "Number of bonus courses"],
  ]) {
    await page.getByRole("button", { name: label, exact: true }).hover()
    await expect(
      page.getByRole("tooltip").filter({ hasText: explanation }),
    ).toBeVisible()
  }
  await page
    .getByRole("button", { name: "1st Med WR Gap", exact: true })
    .click()
  await expect(
    page.locator('[data-testid^="map-card-"]').first(),
  ).toHaveAttribute("data-testid", "map-card-kz_pick_02")
  await expect(
    page.getByRole("button", { name: "1st Med WR Gap: 5.00x", exact: true }),
  ).toBeVisible()
  await page
    .getByRole("button", { name: "1st Med WR Gap", exact: true })
    .click()
  await expect(
    page.locator('[data-testid^="map-card-"]').first(),
  ).toHaveAttribute("data-testid", "map-card-kz_pick_03")
  await expect(
    page.getByRole("button", { name: "1st Med WR Gap: 1.25x", exact: true }),
  ).toBeVisible()
  await page
    .getByRole("button", { name: "1st Med WR Gap: 1.25x", exact: true })
    .focus()
  await expect(page.getByRole("tooltip")).toContainText(
    "Higher values mean a wider gap",
  )
  await page.getByRole("button", { name: "Options", exact: true }).click()
  for (const label of [
    "Reviews",
    "World record",
    "Created and updated",
    "Authors",
    "Skill breakdown",
  ]) {
    await page
      .getByRole("menuitemcheckbox", { name: label, exact: true })
      .click()
  }
  await page.keyboard.press("Escape")
  await expect(page.getByLabel("World record summary")).toHaveCount(0)
  await expect(page.getByLabel("Review summary")).toHaveCount(0)
  await page.reload()
  await expect(page.getByLabel("Skill breakdown")).toHaveCount(0)
  await page.screenshot({
    path: "../.temp/screenshots/maps-options.png",
    fullPage: false,
  })
  expect(requests).toEqual([])
})

test("PB errors do not classify all maps as unfinished", async ({ page }) => {
  await install(page, { failPb: true })
  await page.goto("/maps")
  await completion(page, "Unfinished")
  await expect(
    page.getByText("Unable to load your map completion data."),
  ).toBeVisible()
  await expect(page.locator('[data-testid^="map-card-"]')).toHaveCount(0)
  await expect(page.getByText("No maps found")).toHaveCount(0)
})

test("card controls toggle milliseconds and clear completion selections", async ({
  page,
}) => {
  await install(page)
  await page.goto("/maps")
  await expect(page.getByTestId("map-pb-1")).toHaveText("PB: 0:30.000")
  await expect(page.getByTestId("map-points-1")).toHaveText("970")
  const firstCard = page.getByTestId("map-card-kz_pick_00")
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 })
    const name = await firstCard.locator("h2 a").boundingBox()
    const tier = await firstCard.locator('h2 [data-slot="badge"]').boundingBox()
    const points = await page.getByTestId("map-points-1").boundingBox()
    expect(name).not.toBeNull()
    expect(tier).not.toBeNull()
    expect(points).not.toBeNull()
    if (!name || !tier || !points) throw new Error("Missing map header element")
    const center = name.y + name.height / 2
    expect(Math.abs(tier.y + tier.height / 2 - center)).toBeLessThan(1)
    expect(Math.abs(points.y + points.height / 2 - center)).toBeLessThan(1)
    expect(name.x + name.width).toBeLessThanOrEqual(tier.x)
    expect(tier.x + tier.width).toBeLessThanOrEqual(points.x)
  }
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.getByRole("button", { name: "Options", exact: true }).click()
  await expect(
    page.getByRole("menuitemcheckbox", { name: "Show points", exact: true }),
  ).toBeChecked()
  await page
    .getByRole("menuitemcheckbox", { name: "Show points", exact: true })
    .click()
  await expect(page.getByTestId("map-points-1")).toHaveCount(0)
  await page
    .getByRole("menuitemcheckbox", { name: "Show milliseconds", exact: true })
    .click()
  await page.keyboard.press("Escape")
  await expect(page.getByTestId("map-pb-1")).toHaveText("PB: 0:30")
  await completion(page, "Finished")
  await expect(
    page.getByRole("button", { name: "Finished", exact: true }),
  ).toHaveClass(/text-primary/)
  const runControls = page.getByRole("group", { name: "My Runs", exact: true })
  await expect(
    runControls.getByRole("button", { name: "Unfinished", exact: true }),
  ).toHaveCount(0)
  await expect(page.getByText("3 / 30", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Finished", exact: true }).click()
  await expect(page.getByText("30 / 30", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "TPs", exact: true }).click()
  await expect(page.getByTestId("map-card-kz_pick_27")).toContainText("TPs: 1")
  await expect(page.getByTestId("map-card-kz_pick_02")).not.toContainText(
    "TPs:",
  )
  await expect(page.getByTestId("map-points-3")).toHaveCount(0)
  await expect(page.getByTestId("map-pb-3")).toHaveText("Unfinished")
  const header = page.getByTestId("map-card-kz_pick_00").locator("h2")
  await expect(header).toHaveText("kz_pick_00T3")
  await page.getByRole("button", { name: "PB Date", exact: true }).click()
  await expect(
    page
      .getByTestId("map-card-kz_pick_00")
      .getByText("PB Date: 2026-01-01", { exact: true }),
  ).toBeVisible()
  await page.reload()
  await expect(page.getByTestId("map-pb-1")).toHaveText("PB: 0:30")
  await expect(page.getByTestId("map-points-1")).toHaveCount(0)
})

test("every personal sort orders all PBs before missing values in both directions", async ({
  page,
}) => {
  await install(page)
  await page.goto("/maps")
  await expect(page.getByTestId("map-pb-1")).toContainText("0:30.000")
  await page.getByRole("button", { name: "My Runs", exact: true }).click()
  for (const [label, first, reversed] of [
    ["PB Time", 27, 0],
    ["TPs", 27, 0],
    ["Points", 27, 0],
    ["Rating Contribution", 0, 27],
    ["PB Date", 27, 0],
    ["WR Gap", 27, 0],
  ] as const) {
    const sort = page.getByRole("button", { name: label, exact: true })
    await sort.click()
    const cards = page.locator('[data-testid^="map-card-"]')
    await expect(cards.first()).toHaveAttribute(
      "data-testid",
      `map-card-${maps[first].name}`,
    )
    await expect(cards.nth(3)).toHaveAttribute(
      "data-testid",
      "map-card-kz_pick_02",
    )
    await sort.click()
    await expect(cards.first()).toHaveAttribute(
      "data-testid",
      `map-card-${maps[reversed].name}`,
    )
    await expect(cards.nth(3)).toHaveAttribute(
      "data-testid",
      "map-card-kz_pick_02",
    )
  }
})

test("unfinished waits for PBs and follows the PRO eligibility preference", async ({
  page,
}) => {
  await install(page, { wrBased: false })
  let release = () => {}
  const ready = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route("**/v1/records/pb?**", async (route) => {
    await ready
    await route.fallback()
  })
  await page.goto("/maps")
  await completion(page, "Unfinished")
  await expect(page.locator("output")).toHaveText("Loading PBs…")
  await expect(page.locator('[data-testid^="map-card-"]')).toHaveCount(0)
  release()
  await expect(page.getByText("27 / 30", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Use PRO personal bests" }).click()
  await expect(page.getByText("29 / 30", { exact: true })).toBeVisible()
})

test.describe("touch controls", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true })

  test("metric explanations open separately from sorting and cards show one PB", async ({
    page,
  }) => {
    await install(page)
    await page.goto("/maps")
    await expect(page.getByTestId("map-pb-1")).toHaveText("PB: 0:30.000")
    await page.getByRole("button", { name: "Use PRO personal bests" }).tap()
    await expect(page.getByTestId("map-pb-1")).toHaveText("Unfinished")
    await expect(page.getByTestId("map-pb-2")).toHaveText("PB: 0:25.000")
    await page.getByRole("button", { name: "Metrics", exact: true }).tap()
    const field = page.getByRole("button", {
      name: "1st Med WR Gap",
      exact: true,
    })
    await page
      .getByRole("button", { name: "Explain 1st Med WR Gap", exact: true })
      .tap()
    await expect(page.getByRole("dialog")).toContainText("median PB / WR")
    await expect(field).toHaveAttribute("aria-pressed", "false")
    await page.keyboard.press("Escape")
    await field.tap()
    await expect(field).toHaveAttribute("aria-pressed", "true")
    await expect(
      page.getByRole("button", { name: "Explain 1st Med WR Gap", exact: true }),
    ).toHaveCount(25)
    const layout = await page.evaluate(() => ({
      width: innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }))
    expect(layout.scrollWidth).toBeLessThanOrEqual(layout.width)
    await page.screenshot({
      path: "../.temp/screenshots/maps-mobile.png",
      fullPage: false,
    })
  })
})

test("WR ratio formatting truncates at the requested precision", () => {
  for (const [value, label] of [
    [1, "1.00x"],
    [1.0256, "1.02x"],
    [9.999, "9.99x"],
    [10, "10.00x"],
    [10.001, "10.0x"],
    [10.999, "10.9x"],
    [125.678, "125.6x"],
  ] as const)
    expect(formatWrGap(value)).toBe(label)
  expect(wrGapScaleToRatio(0)).toBe(2)
  expect(wrGapScaleToRatio(-2)).toBe(1.25)
  expect(wrGapScaleToRatio(Number.POSITIVE_INFINITY)).toBeNull()
})

for (const width of [1280, 390]) {
  test(`map presets save, restore, replace, and delete catalog views at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 })
    await install(page)
    await page.goto("/maps")
    await page.getByRole("button", { name: "Use PRO personal bests" }).click()
    await completion(page, "Unfinished")
    await page.getByRole("button", { name: "Metrics", exact: true }).click()
    await page
      .getByRole("button", { name: "NUB Finishers", exact: true })
      .click()
    await page.getByRole("button", { name: "Options", exact: true }).click()
    await page
      .getByRole("menuitemcheckbox", { name: "Reviews", exact: true })
      .click()
    await page.keyboard.press("Escape")
    await page
      .getByRole("textbox", { name: "Search maps by name" })
      .fill("kz_pick_00")
    await page.getByRole("button", { name: "Presets", exact: true }).click()
    await expect(page.getByText("No saved presets yet.")).toBeVisible()
    await page.getByRole("menuitem", { name: "Save current view" }).click()
    await expect(
      page.getByRole("textbox", { name: "Preset name" }),
    ).toHaveValue("Preset 1")
    await page.getByRole("textbox", { name: "Preset name" }).fill("My maps")
    await page.getByRole("button", { name: "Save preset", exact: true }).click()
    await page.reload()
    await page.getByRole("button", { name: "Presets", exact: true }).click()
    await page.getByRole("menuitem", { name: "Reset view" }).click()
    await expect(
      page.getByRole("textbox", { name: "Search maps by name" }),
    ).toHaveValue("")
    await expect(
      page.getByRole("button", { name: "Use PRO personal bests" }),
    ).toHaveText("NUB")
    await expect(page.getByLabel("Review summary").first()).toBeVisible()
    await page.getByRole("button", { name: "Presets", exact: true }).click()
    await page.getByRole("menuitem", { name: "Apply preset My maps" }).click()
    await expect(
      page.getByRole("textbox", { name: "Search maps by name" }),
    ).toHaveValue("kz_pick_00")
    await expect(
      page.getByRole("button", { name: "Use PRO personal bests" }),
    ).toHaveText("PRO")
    await expect(
      page.getByRole("button", { name: "Unfinished", exact: true }),
    ).toHaveAttribute("aria-pressed", "true")
    await expect(
      page.getByRole("button", { name: "NUB Finishers", exact: true }),
    ).toHaveAttribute("aria-pressed", "true")
    await expect(page.getByLabel("Review summary")).toHaveCount(0)
    await page
      .getByRole("textbox", { name: "Search maps by name" })
      .fill("kz_pick_02")
    await page.getByRole("button", { name: "Presets", exact: true }).click()
    await page.getByRole("menuitem", { name: "Save current view" }).click()
    await page.getByRole("textbox", { name: "Preset name" }).fill("my MAPS")
    await page.getByRole("button", { name: "Save preset", exact: true }).click()
    await page.reload()
    await page.getByRole("button", { name: "Presets", exact: true }).click()
    await expect(
      page.getByRole("menuitem", { name: /^Apply preset / }),
    ).toHaveCount(1)
    await page.getByRole("menuitem", { name: "Reset view" }).click()
    await page.getByRole("button", { name: "Presets", exact: true }).click()
    await page.getByRole("menuitem", { name: "Apply preset my MAPS" }).click()
    await expect(
      page.getByRole("textbox", { name: "Search maps by name" }),
    ).toHaveValue("kz_pick_02")
    await page.getByRole("button", { name: "Presets", exact: true }).click()
    await page.screenshot({
      path: `../.temp/screenshots/maps-presets-${width}.png`,
    })
    await page.getByRole("button", { name: "Delete preset my MAPS" }).click()
    await expect(page.getByText("No saved presets yet.")).toBeVisible()
    await page.keyboard.press("Escape")
    await page.reload()
    await page.getByRole("button", { name: "Presets", exact: true }).click()
    await expect(page.getByText("No saved presets yet.")).toBeVisible()
  })
}

test("map presets ignore invalid storage and report failed saves", async ({
  page,
}) => {
  await install(page, { guest: true })
  await page.addInitScript(() => {
    localStorage.setItem(
      "gokz-maps-presets-v1",
      JSON.stringify({
        version: 1,
        presets: [null, { id: "bad", name: "Broken", settings: {} }],
      }),
    )
    const originalSetItem = Storage.prototype.setItem
    Storage.prototype.setItem = function (key, value) {
      if (key === "gokz-maps-presets-v1") throw new Error("Storage unavailable")
      return originalSetItem.call(this, key, value)
    }
  })
  await page.goto("/maps")
  await page.getByRole("button", { name: "Presets", exact: true }).click()
  await expect(page.getByText("No saved presets yet.")).toBeVisible()
  await page.getByRole("menuitem", { name: "Save current view" }).click()
  await page.getByRole("button", { name: "Save preset", exact: true }).click()
  await expect(
    page.getByText("Could not save presets in this browser."),
  ).toBeVisible()
  await expect(page.getByRole("dialog", { name: "Save preset" })).toBeVisible()
})

test("maps default view overrides session state until cleared", async ({
  page,
}) => {
  await install(page)
  await page.goto("/maps")
  await page
    .getByRole("textbox", { name: "Search maps by name" })
    .fill("kz_pick_02")
  await page.getByRole("button", { name: "Use PRO personal bests" }).click()
  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "SKZ" }).click()
  await page.getByRole("button", { name: "Presets", exact: true }).click()
  await page
    .getByRole("menuitem", { name: "Set as default", exact: true })
    .click()
  await page
    .getByRole("textbox", { name: "Search maps by name" })
    .fill("changed")
  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "OVR" }).click()
  await expect(
    page.getByRole("button", { name: "Select record scope" }),
  ).toHaveText("OVR")
  await page.reload()
  await expect(
    page.getByRole("textbox", { name: "Search maps by name" }),
  ).toHaveValue("kz_pick_02")
  await expect(
    page.getByRole("button", { name: "Use PRO personal bests" }),
  ).toHaveText("PRO")
  await expect(
    page.getByRole("button", { name: "Select record scope" }),
  ).toHaveText("SKZ")
  await page.getByRole("button", { name: "Presets", exact: true }).click()
  await page
    .getByRole("menuitem", { name: "Clear default view", exact: true })
    .click()
  await page.getByRole("button", { name: "Presets", exact: true }).click()
  await page.getByRole("menuitem", { name: "Reset view", exact: true }).click()
  await expect(
    page.getByRole("textbox", { name: "Search maps by name" }),
  ).toHaveValue("")
  await page.reload()
  await expect(
    page.getByRole("textbox", { name: "Search maps by name" }),
  ).toHaveValue("")
  await expect(
    page.getByRole("button", { name: "Use PRO personal bests" }),
  ).toHaveText("NUB")
  await page.getByRole("button", { name: "Presets", exact: true }).click()
  await expect(
    page.getByRole("menuitem", { name: "Clear default view", exact: true }),
  ).toHaveCount(0)
})

test("unrated maps keep three star rows and match rated review heights", async ({
  page,
}) => {
  await install(page, { guest: true })
  await page.route(/\/v1\/maps(\?.*)?$/, (route) =>
    route.fulfill({
      json: maps.map((map, index) =>
        index === 0
          ? {
              ...map,
              review_summary: {
                overall_avg: 4.5,
                overall_adjusted: 4.5,
                gameplay_avg: 4,
                visuals_avg: 5,
                reviews_count: 2,
                gameplay_count: 2,
                visuals_count: 1,
                comments_count: 1,
              },
            }
          : map,
      ),
    }),
  )
  await page.goto("/maps")
  const rated = page
    .getByTestId("map-card-kz_pick_00")
    .getByRole("region", { name: "Review summary" })
  const unrated = page
    .getByTestId("map-card-kz_pick_01")
    .getByRole("region", { name: "Review summary" })
  await expect(rated.getByRole("img")).toHaveCount(3)
  await expect(
    unrated.getByRole("img", {
      name: "No rating provided, 0 out of 5 stars",
      exact: true,
    }),
  ).toHaveCount(3)
  await expect(unrated.getByText("(0)", { exact: true })).toHaveCount(3)
  await expect(unrated).toContainText("0 ratings · 0 comments")
  await expect(
    unrated.getByText("No reviews yet", { exact: true }),
  ).toHaveCount(0)
  expect((await unrated.boundingBox())?.height).toBe(
    (await rated.boundingBox())?.height,
  )
  await page.screenshot({ path: "../.temp/screenshots/maps-unrated-stars.png" })
})
