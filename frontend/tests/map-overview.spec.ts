import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })
const map = {
  id: 980250,
  name: "kz_overview",
  validated: true,
  tiers: { OVR: 2, KZT: 2, SKZ: 3, VNL: 4 },
  bonus_count: 2,
  filesize: 1234,
  authors: [],
  no_steamid_names: ["Mapper"],
  created_on: "2020-10-30T01:52:00Z",
  updated_on: "2020-10-30T01:52:00Z",
  review_summary: {
    overall_avg: 4.5,
    gameplay_avg: 4,
    visuals_avg: null,
    reviews_count: 12,
    gameplay_count: 10,
    visuals_count: 0,
    comments_count: 3,
    updated_at: "2026-10-25T12:00:00Z",
  },
  skills: {
    ladder: 0.2,
    bhop: 0.2,
    slide: 0.15,
    climb: 0.15,
    strafe: 0.15,
    boxtech: 0.1,
  },
}
const entry = {
  map: { id: map.id, name: map.name },
  total_finishes: 12345,
  total_playtime: 36000,
  unique_nub_finishes: 100,
  unique_pro_finishes: 25,
  pro_nub_ratio: 0.25,
  median_first_completion_time: 300,
  median_first_finish_time: 500,
  average_finishes_per_player: 12.34,
  average_playtime_per_player: 360,
  updated_at: "2026-10-25T12:00:00Z",
}
async function mockOverview(
  page: Page,
  options: {
    empty?: boolean
    metricsStatus?: number
    wrTime?: number | null
    uncached?: boolean
    authenticated?: boolean
  } = {},
) {
  await page.addInitScript(
    ({ authenticated }) => {
      localStorage.setItem("gokz-language", "en")
      localStorage.setItem("gokz-app-scope", "OVR")
      if (authenticated) localStorage.setItem("access_token", "mock-session")
    },
    { authenticated: options.authenticated ?? false },
  )
  await page.route("**/v1/**", (route) =>
    route.fulfill({ json: { data: [], count: 0 } }),
  )
  await page.route("**/v1/users/me", (route) =>
    route.fulfill({ json: { steamid64: "76561198000000001", roles: [] } }),
  )
  await page.route("**/v1/graphql", (route) =>
    route.fulfill({ json: { data: { mapImages: [], players: [] } } }),
  )
  await page.route(/\/v1\/maps(?:\?.*)?$/, (route) =>
    route.fulfill({
      json: [
        {
          ...map,
          ...(options.empty ? { review_summary: null, skills: null } : {}),
        },
      ],
    }),
  )
  await page.route("**/v1/regions", (route) =>
    route.fulfill({
      json: {
        data: [{ code: "EU", name: "Europe", country_codes: ["DE"] }],
        count: 1,
      },
    }),
  )
  const metricRequests: URL[] = []
  await page.route(/\/v1\/leaderboards\/maps(?:\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    metricRequests.push(url)
    return route.fulfill({
      status: options.metricsStatus ?? 200,
      json: {
        data: [
          {
            ...entry,
            total_finishes:
              url.searchParams.get("scope") === "SKZ"
                ? 42
                : entry.total_finishes,
            ...(options.uncached ? { updated_at: null } : {}),
          },
        ],
        count: 1,
      },
    })
  })
  const wrRequests: URL[] = []
  await page.route(/\/v1\/maps\/wrs(?:\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    wrRequests.push(url)
    const time =
      url.searchParams.get("type") === "PRO"
        ? 150
        : options.wrTime === undefined
          ? 100
          : options.wrTime
    return route.fulfill({ json: time == null ? [] : [{ time }] })
  })
  await page.route(/\/v1\/maps\/\d+\/leaderboard(?:\?.*)?$/, (route) =>
    route.fulfill({
      json: {
        data: [],
        count: 0,
        unique_nub_finishes: 100,
        unique_pro_finishes: 25,
        current_user_rank: null,
        current_user_steamid64: null,
      },
    }),
  )
  await page.route(/\/v1\/maps\/\d+\/stats(?:\?.*)?$/, (route) =>
    route.fulfill({
      json: { nub_wr_gap_distribution: [], pro_wr_gap_distribution: [] },
    }),
  )
  return { metricRequests, wrRequests }
}
function overview(page: Page) {
  return page.getByRole("region", { name: "Map overview", exact: true })
}
function metric(page: Page, label: string) {
  return overview(page)
    .getByRole("region", { name: "Map metrics", exact: true })
    .locator("dl > div")
    .filter({ has: page.getByRole("button", { name: label, exact: true }) })
    .locator("dd")
}
test("map overview shows reviews, complete skills, and essential metrics inside the existing card", async ({
  page,
}) => {
  const { metricRequests } = await mockOverview(page)
  await page.goto(`/maps/${map.name}/maptop`)
  await expect(
    overview(page).getByRole("heading", { name: map.name }),
  ).toBeVisible()
  await expect(
    overview(page).getByText("12 ratings · 3 comments"),
  ).toBeVisible()
  await expect(
    overview(page).getByRole("img", { name: "4.5 out of 5 stars" }),
  ).toBeVisible()
  await expect(
    overview(page).getByRole("link", { name: "View reviews" }),
  ).toHaveCount(0)
  await expect(
    overview(page).getByText(/Main course · All players|Metrics updated/),
  ).toHaveCount(0)
  for (const button of await overview(page)
    .getByRole("region", { name: "Map metrics", exact: true })
    .getByRole("button")
    .all()) {
    await expect(button).toHaveCSS("text-decoration-line", "none")
  }
  const skills = overview(page).getByRole("region", { name: "Skill breakdown" })
  const portions = await skills.getByRole("listitem").allTextContents()
  expect(portions).toHaveLength(6)
  expect(
    portions.reduce(
      (total, portion) => total + Number(portion.match(/(\d+)%/)?.[1]),
      0,
    ),
  ).toBe(95)
  expect(
    await skills
      .locator('div[aria-hidden="true"] > div')
      .evaluateAll((segments) =>
        segments.reduce(
          (sum, segment) =>
            sum + Number.parseFloat((segment as HTMLElement).style.width),
          0,
        ),
      ),
  ).toBe(100)
  for (const [label, value] of [
    ["Total Runs", "12,345"],
    ["Recorded Run Time", "10 h"],
    ["Finishers", "100"],
    ["PRO Finishers", "25"],
    ["PRO Share", "25%"],
    ["Median PB Time", "5:00"],
    ["Median PB WR Gap", "3.00x"],
    ["Avg Finishes per Player", "12.34"],
    ["Avg Playtime per Player", "6:00"],
    ["Med 1st Completion Time", "8:20"],
    ["Med 1st Completion WR Gap", "5.00x"],
    ["Bonuses", "2"],
  ]) {
    await expect(metric(page, label)).toHaveText(value)
  }
  expect(metricRequests[0].searchParams.get("map_id")).toBe(String(map.id))
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1100 })
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            document.documentElement.scrollWidth -
            document.documentElement.clientWidth,
        ),
      )
      .toBeLessThanOrEqual(1)
  }
  await page.screenshot({
    path: "../.temp/map-overview/mobile.png",
    fullPage: true,
  })
  await page.setViewportSize({ width: 1440, height: 1100 })
  await page.screenshot({
    path: "../.temp/map-overview/desktop.png",
    fullPage: true,
  })
  await page.getByRole("tab", { name: "Reviews", exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/maps/${map.name}/reviews$`))
  await expect(metric(page, "Total Runs")).toHaveText("12,345")
})
test("map-wide metrics ignore table filters and use the NUB WR in PRO view", async ({
  page,
}) => {
  const { metricRequests, wrRequests } = await mockOverview(page, {
    authenticated: true,
  })
  await page.goto(`/maps/${map.name}/maptop?type=PRO`)
  await expect(metric(page, "Median PB WR Gap")).toHaveText("3.00x")
  expect(wrRequests.some((url) => url.searchParams.get("type") === "NUB")).toBe(
    true,
  )
  expect(wrRequests.some((url) => url.searchParams.get("type") === "PRO")).toBe(
    true,
  )
  await page.getByRole("button", { name: "PRO", exact: true }).click()
  await page.getByRole("combobox").filter({ hasText: "Main" }).click()
  await page.getByRole("option", { name: "Bonus 1", exact: true }).click()
  await page.getByRole("button", { name: "Friends", exact: true }).click()
  await expect(metric(page, "Total Runs")).toHaveText("12,345")
  await expect(metric(page, "Median PB WR Gap")).toHaveText("3.00x")
  expect(metricRequests).toHaveLength(1)
  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "SKZ", exact: true }).click()
  await expect(metric(page, "Total Runs")).toHaveText("42")
  expect(metricRequests.at(-1)?.searchParams.get("scope")).toBe("SKZ")
})
for (const scenario of ["error", "uncached", "empty"] as const) {
  test(`map overview handles ${scenario} data without blocking the card`, async ({
    page,
  }) => {
    await mockOverview(page, {
      empty: true,
      metricsStatus: scenario === "error" ? 503 : 200,
      uncached: scenario === "uncached",
    })
    if (scenario === "empty")
      await page.route(/\/v1\/leaderboards\/maps(?:\?.*)?$/, (route) =>
        route.fulfill({ json: { data: [], count: 0 } }),
      )
    await page.goto(`/maps/${map.name}/maptop`)
    await expect(overview(page).getByText("No reviews yet")).toBeVisible()
    await expect(overview(page).getByRole("listitem")).toHaveText([
      "Unknown100%",
    ])
    await expect(metric(page, "Total Runs")).toHaveText("—")
    await expect(metric(page, "Median PB WR Gap")).toHaveText("—")
    await expect(metric(page, "Bonuses")).toHaveText("2")
    await expect(overview(page).getByText("Metrics unavailable")).toBeVisible()
    await expect(
      page.getByRole("tab", { name: "Map Top", exact: true }),
    ).toBeVisible()
  })
}
for (const wrTime of [null, 300, 0]) {
  test(`median PB WR gap handles NUB WR ${wrTime}`, async ({ page }) => {
    await mockOverview(page, { wrTime })
    await page.goto(`/maps/${map.name}/maptop?type=PRO`)
    await expect(metric(page, "Median PB WR Gap")).toHaveText(
      wrTime === 300 ? "1.00x" : "—",
    )
    await expect(metric(page, "Total Runs")).toHaveText("12,345")
  })
}
test("metrics loading leaves map details and reviews usable", async ({
  page,
}) => {
  await mockOverview(page)
  let release!: () => void
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route(/\/v1\/leaderboards\/maps(?:\?.*)?$/, async (route) => {
    await pending
    await route.fulfill({ json: { data: [entry], count: 1 } })
  })
  await page.goto(`/maps/${map.name}/maptop`)
  try {
    await expect(
      overview(page).getByRole("heading", { name: map.name }),
    ).toBeVisible()
    await expect(
      overview(page).getByText("12 ratings · 3 comments"),
    ).toBeVisible()
    await expect(
      overview(page).getByRole("region", { name: "Map metrics" }),
    ).toHaveAttribute("aria-busy", "true")
    await expect(metric(page, "Bonuses")).toHaveText("2")
  } finally {
    release()
  }
  await expect(metric(page, "Total Runs")).toHaveText("12,345")
})
test("metric explanations work with keyboard focus", async ({ page }) => {
  await mockOverview(page)
  await page.goto(`/maps/${map.name}/maptop`)
  await overview(page)
    .getByRole("button", { name: "Median PB Time", exact: true })
    .focus()
  await expect(page.getByRole("tooltip")).toContainText("each player’s fastest")
})
test("metric explanations work on touch devices", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  })
  const page = await context.newPage()
  await mockOverview(page)
  await page.goto(`/maps/${map.name}/maptop`)
  await overview(page)
    .getByRole("button", { name: "Explain Median PB Time", exact: true })
    .tap()
  await expect(page.getByRole("dialog")).toContainText("each player’s fastest")
  await context.close()
})

test("saving a review refreshes the summary in the shared map card", async ({
  page,
}) => {
  await mockOverview(page, { authenticated: true })
  let saved = false
  let mapReads = 0
  await page.route(/\/v1\/maps(?:\?.*)?$/, (route) => {
    mapReads += 1
    return route.fulfill({
      json: [
        {
          ...map,
          review_summary: {
            ...map.review_summary,
            overall_avg: saved ? 5 : 4.5,
          },
        },
      ],
    })
  })
  await page.route(/\/v1\/maps\/reviews(?:\?.*)?$/, (route) => {
    if (route.request().method() === "PUT") {
      saved = true
      return route.fulfill({
        json: {
          map_id: map.id,
          steamid64: "76561198000000001",
          server_group_id: null,
          content: { overall: 5, gameplay: null, visuals: null, comment: null },
          created_at: "2026-10-26T12:00:00Z",
          updated_at: "2026-10-26T12:00:00Z",
          player: { steamid64: "76561198000000001", display_name: "Reviewer" },
          map: { id: map.id, name: map.name },
        },
      })
    }
    return route.fulfill({ json: { data: [], count: 0 } })
  })
  await page.goto(`/maps/${map.name}/reviews`)
  await expect(
    overview(page).getByRole("img", { name: "4.5 out of 5 stars" }),
  ).toBeVisible()
  await page.getByTestId("map-add-review-button").click()
  await page.getByTestId("map-review-overall-star-5").click()
  await page.getByRole("button", { name: "Save", exact: true }).click()
  await expect(page.getByRole("dialog")).toHaveCount(0)
  await expect(
    overview(page).getByRole("img", { name: "5 out of 5 stars", exact: true }),
  ).toBeVisible()
  expect(mapReads).toBeGreaterThan(1)
})

test("geographic filters and pagination do not change the map-wide metrics", async ({
  page,
}) => {
  const { metricRequests } = await mockOverview(page)
  const tableRequests: URL[] = []
  await page.route(/\/v1\/maps\/\d+\/leaderboard(?:\?.*)?$/, (route) => {
    tableRequests.push(new URL(route.request().url()))
    return route.fulfill({
      json: {
        data: [],
        count: 40,
        unique_nub_finishes: 100,
        unique_pro_finishes: 25,
        current_user_rank: null,
        current_user_steamid64: null,
      },
    })
  })
  await page.goto(`/maps/${map.name}/maptop`)
  await expect(metric(page, "Total Runs")).toHaveText("12,345")
  await page
    .getByRole("button", { name: "Go to next page", exact: true })
    .click()
  await expect
    .poll(() =>
      tableRequests.some((url) => url.searchParams.get("offset") === "20"),
    )
    .toBe(true)
  await page.getByRole("button", { name: "country", exact: true }).click()
  await page.getByRole("button", { name: /Germany/ }).click()
  await expect
    .poll(() =>
      tableRequests.some((url) => url.searchParams.get("country") === "DE"),
    )
    .toBe(true)
  await page.getByRole("combobox").filter({ hasText: "region" }).click()
  await page.getByRole("option", { name: "EU", exact: true }).click()
  await expect
    .poll(() =>
      tableRequests.some((url) => url.searchParams.get("region") === "EU"),
    )
    .toBe(true)
  await expect(metric(page, "Total Runs")).toHaveText("12,345")
  expect(metricRequests).toHaveLength(1)
})

test("cached zero-run metrics show zero counts and unavailable ratios", async ({
  page,
}) => {
  await mockOverview(page)
  await page.route(/\/v1\/leaderboards\/maps(?:\?.*)?$/, (route) =>
    route.fulfill({
      json: {
        data: [
          {
            ...entry,
            total_finishes: 0,
            total_playtime: 0,
            unique_nub_finishes: 0,
            unique_pro_finishes: 0,
            median_first_completion_time: 0,
          },
        ],
        count: 1,
      },
    }),
  )
  await page.goto(`/maps/${map.name}/maptop`)
  await expect(metric(page, "Total Runs")).toHaveText("0")
  await expect(metric(page, "Recorded Run Time")).toHaveText("0:00")
  await expect(metric(page, "Finishers")).toHaveText("0")
  await expect(metric(page, "PRO Share")).toHaveText("—")
  await expect(metric(page, "Median PB Time")).toHaveText("—")
  await expect(metric(page, "Median PB WR Gap")).toHaveText("—")
})

test("distribution ratio labels preserve logarithmic bins and chart geometry", async ({
  page,
}) => {
  await mockOverview(page)
  const distribution = {
    wr_time: 100,
    median_wr_gap: 1,
    total_pb_count: 9,
    plotted_pb_count: 9,
    bins: [
      { label: "-1", lower_bound: -1, upper_bound: -0.5, count: 2 },
      { label: "0", lower_bound: 0, upper_bound: 0.5, count: 3 },
      { label: "1", lower_bound: 1, upper_bound: 1.5, count: 4 },
    ],
  }
  await page.route(/\/v1\/maps\/\d+\/stats(?:\?.*)?$/, (route) =>
    route.fulfill({
      json: {
        map_id: map.id,
        scope: "OVR",
        updated_at: entry.updated_at,
        nub_wr_gap_distribution: distribution,
        pro_wr_gap_distribution: distribution,
      },
    }),
  )
  await page.goto(`/maps/${map.name}/stats`)
  await expect(page.getByText("Median: 3.00x (5:00)")).toHaveCount(2)
  const chartElement = page.getByTestId("map-stats-nub-wr-gap-chart")
  await expect(chartElement.locator("canvas")).toBeVisible()
  const moduleSource = await (
    await page.request.get("/src/components/Maps/MapStatsSection.tsx")
  ).text()
  const echartsUrl = moduleSource.match(
    /import\s+\*\s+as\s+echarts\s+from\s+["']([^"']+)["']/,
  )?.[1]
  expect(echartsUrl).toBeTruthy()
  const result = await chartElement.evaluate(async (element, moduleUrl) => {
    // Inspect the same ECharts module instance as the rendered component.
    const echarts = await import(moduleUrl)
    const chart = echarts.getInstanceByDom(element)
    const option = chart.getOption()
    return {
      min: option.xAxis[0].min,
      max: option.xAxis[0].max,
      interval: option.xAxis[0].interval,
      inverse: option.xAxis[0].inverse,
      data: option.series[0].data,
      labels: [-1, 0, 1].map((value) =>
        option.xAxis[0].axisLabel.formatter(value),
      ),
      tooltip: option.tooltip[0].formatter({ dataIndex: 1, value: [0.25, 3] }),
    }
  }, echartsUrl!)
  expect(result).toMatchObject({
    min: -5,
    max: 7.5,
    interval: 0.5,
    inverse: true,
    data: [
      [-0.75, 2],
      [0.25, 3],
      [1.25, 4],
    ],
  })
  expect(result.labels).toEqual([
    "{gap|1.50x}\n{time|2:30}",
    "{gap|2.00x}\n{time|3:20}",
    "{gap|3.00x}\n{time|5:00}",
  ])
  expect(result.tooltip).toContain("2.00x ~ 2.41x")
  await chartElement.screenshot({
    path: "../.temp/map-overview/distribution-ratio.png",
  })
})
