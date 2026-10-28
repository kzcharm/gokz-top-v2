import { expect, type Page, test } from "@playwright/test"
import { mapImagePixel, stubMapImageAssets } from "./utils/mapImages"

test.use({ storageState: { cookies: [], origins: [] } })

const steamid64 = "76561198000000001"

const seededPlayer = {
  name: "Seed Runner",
  alias: "Seed Alias",
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2026-03-01T12:00:00Z",
  last_played_at: "2026-03-31T12:00:00Z",
  updated_at: "2026-03-31T12:00:00Z",
  steamid64,
}

const profileViews = 3

const defaultSkillRatings = {
  boxtech: { raw_rating: 1200, rating: 2.25 },
  strafe: { raw_rating: 2400, rating: 3.5 },
  bhop: { raw_rating: 3600, rating: 4.75 },
  climb: { raw_rating: 4800, rating: 6 },
  ladder: { raw_rating: 0, rating: null },
  slide: { raw_rating: 6000, rating: 7.25 },
}

async function installProfileShellRoutes(
  page: Page,
  skillRatings: Record<
    string,
    { raw_rating: number; rating: number | null }
  > = defaultSkillRatings,
) {
  await stubMapImageAssets(page)
  await page.route("**/v1/graphql", async (route) => {
    const body = route.request().postDataJSON()
    if (!body.query?.includes("query MapImages")) return route.fallback()
    await route.fulfill({
      json: {
        data: {
          mapImages: body.variables.inputs.map(
            (input: { mapName: string; workshopId?: string }) => ({
              ...input,
              workshopId: input.workshopId ?? null,
              previewUrl: `${new URL(route.request().url()).origin}/v1/maps/images/${encodeURIComponent(input.mapName)}.webp`,
            }),
          ),
        },
      },
    })
  })
  await page.route(/\/v1\/users\/me$/, async (route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Unauthorized" }),
    })
  })

  await page.route(/\/v1\/players\/[^/]+$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seededPlayer),
    })
  })

  await page.route(/\/v1\/players\/[^/]+\/views$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ profile_views: profileViews }),
    })
  })

  await page.route(/\/v1\/players\/[^/]+\/stats(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        steamid64,
        daily_activity: null,
        playtime: {
          updated_at: "2026-04-03T12:00:00Z",
          total_seconds: 7200,
        },
      }),
    })
  })

  await page.route(/\/v1\/players\/[^/]+\/follow-summary$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        follower_count: 0,
        following_count: 0,
        viewer_is_following: null,
        viewer_is_self: false,
      }),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/pinned-records(\?.*)?$/,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      })
    },
  )

  await page.route(/\/v1\/players\/[^/]+\/jumpstats(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [],
        count: 0,
      }),
    })
  })

  await page.route(/\/v1\/bans(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })

  await page.route(/\/v1\/maps(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  })

  await page.route(
    /\/v1\/leaderboards\/players\/[^/?]+(\?.*)?$/,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rank: 42,
          rank_regional: 7,
          region: "EU",
          rating: 5.5,
          skill_ratings: skillRatings,
        }),
      })
    },
  )
}

const ovrRecords = [
  {
    uuid: "019d7777-7777-7777-8777-777777777777",
    id: 981100,
    steamid64,
    player_name: "Seed Runner",
    player_avatar_hash: null,
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    server_group: {
      id: "11111111-1111-4111-8111-111111111111",
      name: "Seed Server Group",
      custom_id: "seed-server-group",
    },
    map_id: 980200,
    map_name: "kz_seed_alpha",
    workshop_id: 1986459033,
    map_tier: 4,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time: 42.123,
    teleports: 0,
    points: 350,
    raw_rating_contribution: 17,
    created_on: "2026-03-30T12:00:00Z",
    updated_on: "2026-03-30T12:00:00Z",
    updated_by: steamid64,
    replay_id: 123,
    is_valid: true,
  },
  {
    uuid: "019d8888-8888-7888-8888-888888888888",
    id: 981101,
    steamid64,
    player_name: "Seed Runner",
    player_avatar_hash: null,
    steam_id: null,
    server_id: 980301,
    server_name: "Second Server",
    map_id: 980201,
    map_name: "kz_seed_beta",
    workshop_id: null,
    map_tier: 6,
    mode_id: 201,
    mode: "SKZ",
    stage: 0,
    tickrate: 128,
    time: 50.456,
    teleports: 3,
    points: 510,
    raw_rating_contribution: 25,
    created_on: "2026-03-31T12:00:00Z",
    updated_on: "2026-03-31T12:00:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
  {
    uuid: "019d9999-9999-7999-8999-999999999999",
    id: 981102,
    steamid64,
    player_name: "Seed Runner",
    player_avatar_hash: null,
    steam_id: null,
    server_id: 980302,
    server_name: "NKZ Practice Hub",
    map_id: 980202,
    map_name: "kz_seed_gamma",
    workshop_id: null,
    map_tier: 2,
    mode_id: 202,
    mode: "NKZ",
    stage: 0,
    tickrate: 128,
    time: 61.234,
    teleports: 8,
    points: 120,
    raw_rating_contribution: 6,
    created_on: "2026-03-29T12:00:00Z",
    updated_on: "2026-03-29T12:00:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
]

test("Development profile routes use regular modules instead of virtual split imports", async ({
  request,
}) => {
  for (const route of ["index", "runs"]) {
    const response = await request.get(
      `/src/routes/_layout/profile.$identifier.${route}.tsx`,
    )
    expect(response.ok()).toBeTruthy()
    const source = await response.text()
    expect(source).toContain("ProfilePage")
    expect(source).not.toContain("tsr-split=")
    expect(source).not.toContain("lazyRouteComponent")
  }
})

test("Profile runs switch between automatic loading and remembered pagination", async ({
  page,
}) => {
  await installProfileShellRoutes(page)
  const records = Array.from({ length: 125 }, (_, index) => ({
    ...ovrRecords[0],
    uuid: `019d7777-7777-7777-8777-${String(index).padStart(12, "0")}`,
    map_id: 980200 + index,
    map_name: `kz_pagination_${String(index).padStart(3, "0")}`,
    time: index + 1,
  }))
  await page.route(/\/v1\/records\/pb(\?.*)?$/, (route) =>
    route.fulfill({ json: records }),
  )
  await page.goto(`/profile/${steamid64}/runs`)
  const rows = page.locator('[data-testid^="pb-record-row-"]')
  await expect(rows).toHaveCount(50)
  await page
    .getByText("Loading more records...", { exact: true })
    .scrollIntoViewIfNeeded()
  await expect.poll(() => rows.count()).toBeGreaterThanOrEqual(100)

  await page.getByRole("button", { name: "Record page settings" }).click()
  await expect(
    page.getByRole("menuitemradio", { name: "Auto-load more", exact: true }),
  ).toBeChecked()
  await page
    .getByRole("menuitemradio", { name: "Pagination", exact: true })
    .click()
  await expect(rows).toHaveCount(50)
  const recordsTable = page.getByTestId("pb-records-table")
  const currentPage = recordsTable.getByRole("spinbutton", {
    name: /Current page/,
  })
  await expect(
    recordsTable.getByRole("button", { name: "Go to next page", exact: true }),
  ).toBeVisible()
  await expect(currentPage).toHaveValue("1")
  await expect(
    page.getByText("Loading more records...", { exact: true }),
  ).toHaveCount(0)
  const firstMap = await rows.first().textContent()
  await page
    .getByRole("button", { name: "Go to next page", exact: true })
    .click()
  await expect(currentPage).toHaveValue("2")
  await expect(rows).toHaveCount(50)
  expect(await rows.first().textContent()).not.toBe(firstMap)
  await page
    .getByRole("button", { name: "Go to last page", exact: true })
    .click()
  await expect(currentPage).toHaveValue("3")
  await expect(rows).toHaveCount(25)
  await currentPage.fill("2")
  await currentPage.press("Enter")
  await expect(rows).toHaveCount(50)

  await page.getByRole("combobox").filter({ hasText: "50" }).click()
  await page.getByRole("option", { name: "20", exact: true }).click()
  await expect(currentPage).toHaveValue("1")
  await expect(rows).toHaveCount(20)
  await page.reload()
  await expect(rows).toHaveCount(20)
  await expect(
    page.getByRole("combobox").filter({ hasText: "20" }),
  ).toBeVisible()
  await page
    .getByRole("button", { name: "Go to last page", exact: true })
    .click()
  await expect(rows).toHaveCount(5)
  await page
    .getByRole("textbox", { name: "Search map name" })
    .fill("kz_pagination_000")
  await expect(rows).toHaveCount(1)
  await expect(currentPage).toHaveValue("1")
  await page
    .getByRole("textbox", { name: "Search map name" })
    .fill("no-such-map")
  await expect(rows).toHaveCount(0)
  await expect(currentPage).toHaveValue("1")
  await expect(
    page.getByRole("button", { name: "Go to next page", exact: true }),
  ).toBeDisabled()
  await page.getByRole("textbox", { name: "Search map name" }).clear()
  await expect(rows).toHaveCount(20)
  await page.screenshot({
    path: "../.temp/profile-runs/pagination.png",
    fullPage: true,
  })

  await page.getByRole("button", { name: "Record page settings" }).click()
  await page
    .getByRole("menuitemradio", { name: "Auto-load more", exact: true })
    .click()
  await expect(rows).toHaveCount(50)
  await expect(currentPage).toHaveCount(0)
  await page.reload()
  await expect(rows).toHaveCount(50)
  await expect(currentPage).toHaveCount(0)
})

test("Profile runs remember mode and rating column visibility", async ({
  page,
}) => {
  await installProfileShellRoutes(page)
  await page.route(/\/v1\/records\/pb(\?.*)?$/, (route) =>
    route.fulfill({ json: ovrRecords }),
  )
  await page.goto(`/profile/${steamid64}/runs`)
  const table = page.getByTestId("pb-records-table")
  const mode = table.getByRole("columnheader", { name: "Mode", exact: true })
  const rating = table.getByRole("columnheader", { name: /Rating/ })
  await expect(mode).toBeVisible()
  await expect(rating).toBeVisible()

  for (const label of ["Mode", "Rating"]) {
    await page.getByRole("button", { name: "Record page settings" }).click()
    await expect(page.getByText("Display", { exact: true })).toBeVisible()
    await expect(
      page.getByRole("menuitemcheckbox", { name: /^Show / }),
    ).toHaveCount(0)
    const toggle = page.getByRole("menuitemcheckbox", {
      name: label,
      exact: true,
    })
    await expect(toggle).toBeChecked()
    await toggle.press("Space")
  }
  await expect(mode).toHaveCount(0)
  await expect(rating).toHaveCount(0)
  await expect(
    table.getByRole("columnheader", { name: "Points", exact: true }),
  ).toBeVisible()
  await page.reload()
  await expect(
    page.getByTestId(`pb-record-row-${ovrRecords[0].uuid}`),
  ).toBeVisible()
  await expect(mode).toHaveCount(0)
  await expect(rating).toHaveCount(0)

  for (const label of ["Mode", "Rating"]) {
    await page.getByRole("button", { name: "Record page settings" }).click()
    const toggle = page.getByRole("menuitemcheckbox", {
      name: label,
      exact: true,
    })
    await expect(toggle).not.toBeChecked()
    await toggle.press("Space")
  }
  await expect(mode).toBeVisible()
  await expect(rating).toBeVisible()
  await page.screenshot({
    path: "../.temp/screenshots/profile-runs-columns.png",
    fullPage: true,
  })
})

test("First completion times sort the full collection and keep missing dates last", async ({
  page,
}) => {
  await installProfileShellRoutes(page)
  await page.context().addCookies([
    {
      name: "profile_runs_auto_load_more",
      value: "false",
      url: "http://localhost:5173",
    },
  ])
  const records = Array.from({ length: 55 }, (_, index) => ({
    ...ovrRecords[0],
    uuid: `019d7777-7777-7777-8777-${String(index).padStart(12, "0")}`,
    map_id: 980300 + index,
    map_name: `kz_first_${String(index).padStart(3, "0")}`,
    created_on: new Date(Date.UTC(2026, 0, index + 1)).toISOString(),
  }))
  await page.route(/\/v1\/records\/pb(\?.*)?$/, (route) =>
    route.fulfill({ json: records }),
  )
  let requests = 0
  await page.route(/\/v1\/records\/pb\/first-completions\?/, async (route) => {
    requests++
    const url = new URL(route.request().url())
    expect(url.searchParams.get("identifier")).toBe(steamid64)
    expect(url.searchParams.get("scope")).toBe("OVR")
    await route.fulfill({
      json: records.flatMap((record, index) =>
        index === 53
          ? []
          : [
              {
                map_id: record.map_id,
                stage: 0,
                first_completed_at: new Date(
                  Date.UTC(2020, 0, 55 - index),
                ).toISOString(),
              },
            ],
      ),
    })
  })
  await page.goto(`/profile/${steamid64}/runs`)
  const rows = page.locator('[data-testid^="pb-record-row-"]')
  await expect(rows.first()).toHaveAttribute(
    "data-testid",
    `pb-record-row-${records[54].uuid}`,
  )
  expect(requests).toBe(0)
  await page.getByRole("button", { name: "Record page settings" }).click()
  await page
    .getByRole("menuitemcheckbox", {
      name: "First completion time",
      exact: true,
    })
    .click()
  await expect(
    page.getByRole("button", { name: "First completion", exact: true }),
  ).toBeEnabled()
  await expect(rows.first()).toHaveAttribute(
    "data-testid",
    `pb-record-row-${records[54].uuid}`,
  )
  await expect(
    page.getByTestId("pb-record-first-completion").first(),
  ).toContainText("2020")
  await page
    .getByRole("button", { name: "First completion", exact: true })
    .click()
  await expect(rows.first()).toHaveAttribute(
    "data-testid",
    `pb-record-row-${records[0].uuid}`,
  )
  await page
    .getByRole("button", { name: "Go to last page", exact: true })
    .click()
  await expect(rows.last()).toHaveAttribute(
    "data-testid",
    `pb-record-row-${records[53].uuid}`,
  )
  await expect(
    rows.last().getByTestId("pb-record-first-completion"),
  ).toHaveText("-")
  await page
    .getByRole("button", { name: "First completion", exact: true })
    .click()
  await expect(rows.first()).toHaveAttribute(
    "data-testid",
    `pb-record-row-${records[54].uuid}`,
  )
  await page.screenshot({
    path: "../.temp/first-completion/profile-first-completion.png",
    fullPage: true,
  })
  await page
    .getByRole("button", { name: "Go to last page", exact: true })
    .click()
  await expect(rows.last()).toHaveAttribute(
    "data-testid",
    `pb-record-row-${records[53].uuid}`,
  )
  expect(requests).toBe(1)
  await page.getByRole("button", { name: "Record page settings" }).click()
  await page
    .getByRole("menuitemcheckbox", {
      name: "First completion time",
      exact: true,
    })
    .click()
  await expect(page.getByTestId("pb-record-first-completion")).toHaveCount(0)
  await expect(rows.first()).toHaveAttribute(
    "data-testid",
    `pb-record-row-${records[54].uuid}`,
  )
})

test("First completion respects date and clock preferences when PB dates are hidden", async ({
  page,
}) => {
  await installProfileShellRoutes(page)
  await page.addInitScript(() => {
    localStorage.setItem("gokz-datetime-format", "us")
    localStorage.setItem("gokz-hour-cycle", "12h")
  })
  await page.context().addCookies([
    {
      name: "profile_runs_show_date",
      value: "false",
      url: "http://localhost:5173",
    },
  ])
  await page.route(/\/v1\/records\/pb(\?.*)?$/, (route) =>
    route.fulfill({ json: [ovrRecords[0]] }),
  )
  await page.route(/\/v1\/records\/pb\/first-completions\?/, (route) =>
    route.fulfill({
      json: [
        {
          map_id: ovrRecords[0].map_id,
          stage: 0,
          first_completed_at: "2020-02-03T12:34:00Z",
        },
      ],
    }),
  )
  await page.goto(`/profile/${steamid64}/runs`)
  await page.getByRole("button", { name: "Record page settings" }).click()
  await page
    .getByRole("menuitemcheckbox", {
      name: "First completion time",
      exact: true,
    })
    .click()
  await expect(page.getByTestId("pb-record-first-completion")).toContainText(
    "02/03/2020",
  )
  await expect(page.getByTestId("pb-record-first-completion")).toContainText(
    /\d{1,2}:34\s*[AP]M/,
  )
  await expect(
    page.getByRole("button", { name: "Datetime", exact: true }),
  ).toHaveCount(0)
})

test("First completion loading and retry leave normal records available", async ({
  page,
}) => {
  await installProfileShellRoutes(page)
  await page.route(/\/v1\/records\/pb(\?.*)?$/, (route) =>
    route.fulfill({ json: ovrRecords.slice(0, 2) }),
  )
  let release: (() => void) | undefined
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  let requests = 0
  await page.route(/\/v1\/records\/pb\/first-completions\?/, async (route) => {
    requests++
    if (requests === 1) {
      await gate
      await route.fulfill({ status: 503, json: { detail: "Unavailable" } })
    } else {
      await route.fulfill({
        json: [
          {
            map_id: ovrRecords[0].map_id,
            stage: 0,
            first_completed_at: "2020-01-01T12:00:00Z",
          },
        ],
      })
    }
  })
  await page.goto(`/profile/${steamid64}/runs`)
  await page.getByRole("button", { name: "Record page settings" }).click()
  await page
    .getByRole("menuitemcheckbox", {
      name: "First completion time",
      exact: true,
    })
    .click()
  await expect(page.getByText("Loading first completion times…")).toBeVisible()
  await expect(
    page.getByRole("button", { name: "First completion", exact: true }),
  ).toBeDisabled()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(2)
  release?.()
  await expect(
    page.getByText("Could not load first completion times."),
  ).toBeVisible()
  expect(requests).toBe(1)
  await page.getByRole("button", { name: "Retry", exact: true }).click()
  await expect(
    page.getByRole("button", { name: "First completion", exact: true }),
  ).toBeEnabled()
  await expect(
    page.getByText("Could not load first completion times."),
  ).toHaveCount(0)
  expect(requests).toBe(2)
})

test("First completion is temporary and saved sorts cannot enable its query", async ({
  page,
}) => {
  await installProfileShellRoutes(page)
  await page.addInitScript(() => {
    localStorage.setItem(
      "gokz-profile-record-presets-v1",
      JSON.stringify({
        version: 1,
        presets: [
          {
            id: "first",
            name: "First finish",
            settings: {
              isProOnly: false,
              isBonus: false,
              view: {
                selectedMode: "all",
                selectedTier: "all",
                selectedStage: null,
                sort: { column: "firstCompletion", direction: "asc" },
              },
            },
          },
        ],
      }),
    )
  })
  await page.route(/\/v1\/records\/pb(\?.*)?$/, (route) =>
    route.fulfill({ json: ovrRecords.slice(0, 2) }),
  )
  const requests: URL[] = []
  await page.route(/\/v1\/records\/pb\/first-completions\?/, async (route) => {
    requests.push(new URL(route.request().url()))
    await route.fulfill({ json: [] })
  })
  await page.goto(`/profile/${steamid64}/runs`)
  await page.getByRole("button", { name: "Presets", exact: true }).click()
  await page.getByRole("button", { name: "Apply preset First finish" }).click()
  await expect(page.getByTestId("pb-record-first-completion")).toHaveCount(0)
  expect(requests).toHaveLength(0)
  const enable = async () => {
    await page.getByRole("button", { name: "Record page settings" }).click()
    await page
      .getByRole("menuitemcheckbox", {
        name: "First completion time",
        exact: true,
      })
      .click()
    await expect(
      page.getByRole("button", { name: "First completion", exact: true }),
    ).toBeEnabled()
  }
  await enable()
  await page.locator("#profile-records-pro-only").click()
  await expect.poll(() => requests.at(-1)?.searchParams.get("type")).toBe("PRO")
  await page.locator("#profile-records-bonus").click()
  await expect
    .poll(() => requests.at(-1)?.searchParams.get("is_bonus"))
    .toBe("true")
  await page.getByRole("tab", { name: "Home", exact: true }).click()
  await page.getByRole("tab", { name: "Runs", exact: true }).click()
  await expect(page.getByTestId("pb-record-first-completion")).toHaveCount(0)
  await enable()
  const count = requests.length
  await page.reload()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(2)
  await expect(page.getByTestId("pb-record-first-completion")).toHaveCount(0)
  expect(requests).toHaveLength(count)
  expect(
    (await page.context().cookies()).some((cookie) =>
      cookie.name.includes("first_completion"),
    ),
  ).toBe(false)
})

test("Profile PB ranks are opt-in, scoped, sortable, and remembered", async ({
  page,
}) => {
  await installProfileShellRoutes(page)
  const rankedRequests: URL[] = []
  const allRequests: URL[] = []
  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    allRequests.push(url)
    expect(url.searchParams.has("include_ranks")).toBe(false)
    await route.fulfill({
      json: ovrRecords.slice(0, 2).map((record) => ({
        ...record,
        rank: null,
      })),
    })
  })

  await page.route(/\/v1\/records\/pb\/ranks\?/, async (route) => {
    const url = new URL(route.request().url())
    rankedRequests.push(url)
    expect(url.searchParams.getAll("uuid_list")).toHaveLength(2)
    await route.fulfill({
      json: { [ovrRecords[0].uuid]: 2, [ovrRecords[1].uuid]: 1 },
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)
  await expect(
    page.getByTestId(`pb-record-row-${ovrRecords[0].uuid}`),
  ).toBeVisible()
  expect(allRequests.length).toBeGreaterThan(0)
  expect(rankedRequests).toHaveLength(0)
  await expect(page.getByTestId("pb-record-rank")).toHaveCount(0)

  await page.getByRole("button", { name: "Record page settings" }).click()
  const toggle = page.getByRole("menuitemcheckbox", {
    name: "Ranks",
    exact: true,
  })
  await expect(toggle).not.toBeChecked()
  await toggle.click()
  await expect(page.getByTestId("pb-record-rank").first()).toContainText("#1")
  expect(rankedRequests).toHaveLength(1)
  expect(rankedRequests[0].searchParams.get("type")).toBe("NUB")
  await page.screenshot({
    path: "../.temp/pb-ranks/profile-ranks.png",
    fullPage: true,
  })
  await page.getByRole("button", { name: "Rank", exact: true }).click()
  await expect(page.getByTestId("pb-record-rank").first()).toContainText("#1")
  await page.getByRole("button", { name: "Rank", exact: true }).click()
  await expect(page.getByTestId("pb-record-rank").first()).toContainText("#2")

  await page.reload()
  await expect(page.getByTestId("pb-record-rank")).toHaveCount(2)
  expect(rankedRequests).toHaveLength(2)
  await page.locator("#profile-records-pro-only").click()
  await expect
    .poll(() => rankedRequests.at(-1)?.searchParams.get("type"))
    .toBe("PRO")
  await expect(page.getByTestId("pb-record-rank")).toHaveCount(2)

  await page.getByRole("button", { name: "Record page settings" }).click()
  await page
    .getByRole("menuitemcheckbox", { name: "Ranks", exact: true })
    .click()
  await expect(page.getByTestId("pb-record-rank")).toHaveCount(0)
  const requestCount = rankedRequests.length
  await page.reload()
  await expect(
    page.getByTestId(`pb-record-row-${ovrRecords[0].uuid}`),
  ).toBeVisible()
  expect(rankedRequests).toHaveLength(requestCount)
  await expect(page.getByTestId("pb-record-rank")).toHaveCount(0)
})

test("Profile PB ranks show a dash for unranked records", async ({ page }) => {
  await installProfileShellRoutes(page)
  await page.context().addCookies([
    {
      name: "profile_runs_show_ranks",
      value: "true",
      url: "http://localhost:5173",
    },
  ])
  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({ json: [{ ...ovrRecords[0], rank: null }] })
  })
  await page.route(/\/v1\/records\/pb\/ranks\?/, async (route) => {
    await route.fulfill({ json: { [ovrRecords[0].uuid]: null } })
  })
  await page.goto(`/profile/${steamid64}/runs`)
  await expect(page.getByTestId("pb-record-rank")).toHaveText("—")
})

test("Profile sidebar renders calibrated skill ratings and unavailable skills", async ({
  page,
}) => {
  await installProfileShellRoutes(page)
  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)

  await expect(
    page.getByRole("img", { name: "Relative profile skill radar" }),
  ).toBeVisible()
  await expect(page.locator('[data-skill-label="bhop"]')).toContainText(
    "Bhop 4.75",
  )
  await expect(page.locator('[data-skill-label="ladder"]')).toContainText(
    "Ladder —",
  )
  await expect(
    page.getByRole("button", { name: "How skill ratings work" }),
  ).toHaveCount(0)
})

test("Profile skill radar directly shows the compact relative view", async ({
  page,
}) => {
  const ratings = {
    boxtech: { raw_rating: 7000, rating: 10.99999 },
    strafe: { raw_rating: 7100, rating: 10.9 },
    bhop: { raw_rating: 7200, rating: 10.97 },
    climb: { raw_rating: 7300, rating: 10.98 },
    ladder: { raw_rating: 7150, rating: 10.96 },
    slide: { raw_rating: 7250, rating: 10.97 },
  }
  await installProfileShellRoutes(page, ratings)
  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)

  const polygon = page.getByTestId("profile-skill-radar-polygon")
  const relativePoints = await polygon.getAttribute("points")

  await expect(
    page.getByRole("img", { name: "Relative profile skill radar" }),
  ).toBeVisible()
  await expect(page.getByRole("button", { name: "Relative" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Global" })).toHaveCount(0)
  await expect(
    page.getByText(/absolute strength limits the inner dip/),
  ).toHaveCount(0)
  await expect(page.locator('[data-skill-label="strafe"]')).toContainText(
    "Strafe 10.90",
  )
  await expect(page.locator('[data-skill-label="boxtech"]')).toContainText(
    "Boxtech 10.99",
  )
  await expect(page.locator('[data-skill-label="climb"]')).toContainText(
    "Climb 10.98",
  )

  await expect(page.getByTestId("profile-skill-radar-grid-line")).toHaveCount(4)

  const maximumRadius = (points: string | null) =>
    Math.max(
      ...(points ?? "").split(" ").map((point) => {
        const [x, y] = point.split(",").map(Number)
        return Math.hypot(x - 110, y - 110)
      }),
    )
  expect(maximumRadius(relativePoints)).toBeGreaterThan(70)
  const relativeRadii = (relativePoints ?? "").split(" ").map((point) => {
    const [x, y] = point.split(",").map(Number)
    return Math.hypot(x - 110, y - 110)
  })
  expect(
    Math.min(...relativeRadii) / Math.max(...relativeRadii),
  ).toBeGreaterThan(0.75)

  const chartBox = await page
    .getByRole("img", { name: "Relative profile skill radar" })
    .boundingBox()
  const cardBox = await page
    .getByRole("img", { name: "Relative profile skill radar" })
    .locator("xpath=ancestor::*[contains(@class, 'rounded-[28px]')][1]")
    .boundingBox()
  expect(chartBox?.width).toBe(220)
  expect(chartBox?.width).toBeLessThanOrEqual(cardBox?.width ?? 0)

  for (const skill of [
    "boxtech",
    "strafe",
    "bhop",
    "climb",
    "ladder",
    "slide",
  ]) {
    const label = page.locator(`[data-skill-label="${skill}"]`)
    await expect(label).toHaveCSS("font-size", "10px")
    await expect(label).toHaveAttribute("text-anchor", "middle")
    const labelBox = await label.boundingBox()
    expect(labelBox?.x).toBeGreaterThanOrEqual(cardBox?.x ?? 0)
    expect((labelBox?.x ?? 0) + (labelBox?.width ?? 0)).toBeLessThanOrEqual(
      (cardBox?.x ?? 0) + (cardBox?.width ?? 0),
    )
    expect(labelBox?.y).toBeGreaterThanOrEqual(cardBox?.y ?? 0)
    expect((labelBox?.y ?? 0) + (labelBox?.height ?? 0)).toBeLessThanOrEqual(
      (cardBox?.y ?? 0) + (cardBox?.height ?? 0),
    )
  }
})

test("Profile records page renders sidebar, filters, and scope-aware PB rows", async ({
  page,
}) => {
  const pbRequests: Array<{
    isProOnly: string | null
    scope: string | null
    stage: string | null
    steamid64: string | null
  }> = []

  await installProfileShellRoutes(page)

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const scope = url.searchParams.get("scope")
    const recordType = url.searchParams.get("type")
    const isProOnly =
      url.searchParams.get("is_pro_only") ??
      (recordType === "PRO" ? "true" : recordType === "NUB" ? "false" : null)

    pbRequests.push({
      scope,
      isProOnly,
      stage: url.searchParams.get("stage"),
      steamid64:
        url.searchParams.get("steamid64") ?? url.searchParams.get("identifier"),
    })

    const payload =
      scope === "SKZ" ? [] : isProOnly === "true" ? [ovrRecords[0]] : ovrRecords

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)

  await expect(page.getByRole("link", { name: /Seed Alias/ })).toBeVisible()
  await expect(
    page.getByRole("img", { name: "Profile skill radar" }),
  ).toBeVisible()
  await expect(page.getByRole("tab", { name: "Runs" })).toHaveAttribute(
    "data-state",
    "active",
  )

  await expect(page.getByRole("columnheader", { name: "Map" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Mode" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Tier" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "TPs" })).toBeVisible()
  await expect(
    page.getByRole("columnheader", { name: "Time", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("columnheader", { name: "Points", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("columnheader", { name: /^Rating/ }),
  ).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Server" })).toBeVisible()
  await expect(
    page.getByRole("columnheader", { name: "Datetime" }),
  ).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Player" })).toHaveCount(
    0,
  )

  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  const alphaMapTile = page
    .getByRole("link", { name: "kz_seed_alpha" })
    .locator("div")
    .first()
  await expect(alphaMapTile).toHaveAttribute(
    "style",
    /\/v1\/maps\/images\/kz_seed_alpha\.webp/,
  )
  await expect(
    page.getByRole("link", { name: "Seed Server Group" }),
  ).toHaveAttribute("href", "/servers/group/seed-server-group")
  await expect(page.getByText("Seed Server", { exact: true })).toHaveCount(0)
  await expect(page.getByText("kz_seed_beta")).toBeVisible()
  await expect(page.getByText("kz_seed_gamma")).toBeVisible()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(3)

  await expect(page.getByLabel("Search map name")).toBeVisible()
  await expect(page.getByLabel("Filter by mode")).toBeVisible()
  await expect(page.getByLabel("Filter by tier")).toBeVisible()
  await expect(page.getByLabel("Filter by points range")).toBeVisible()
  await expect(page.getByLabel("Search server")).toBeVisible()

  const headerRow = page
    .getByRole("columnheader", { name: "Map" })
    .locator("xpath=ancestor::tr")
  const filterRow = page
    .getByLabel("Search map name")
    .locator("xpath=ancestor::tr")
  const dataRow = page.locator('[data-testid^="pb-record-row-"]').first()

  await headerRow.hover()
  await expect(headerRow).toHaveCSS("outline-style", "none")
  await filterRow.hover()
  await expect(filterRow).toHaveCSS("outline-style", "none")
  await dataRow.hover()
  await expect(dataRow).toHaveCSS("outline-style", "solid")

  await page.getByLabel("Search map name").fill("gamma")
  await expect(page.getByText("kz_seed_gamma")).toBeVisible()
  await expect(page.getByText("kz_seed_alpha")).toHaveCount(0)
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)

  await page.getByLabel("Search map name").fill("")
  await page.getByLabel("Filter by mode").click()
  await page.getByRole("option", { name: "NKZ" }).click()
  await expect(page.getByText("kz_seed_gamma")).toBeVisible()
  await expect(page.getByText("kz_seed_alpha")).toHaveCount(0)
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)

  await page.getByLabel("Filter by mode").click()
  await page.getByRole("option", { name: "Modes" }).click()
  await page.getByLabel("Filter by tier").click()
  await page.getByRole("option", { name: "T6" }).click()
  await expect(page.getByText("kz_seed_beta")).toBeVisible()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)

  await page.getByLabel("Filter by tier").click()
  await page.getByRole("option", { name: "Tier" }).click()
  await page.getByLabel("Filter by points range").click()
  await page.getByRole("spinbutton", { name: "Minimum points" }).fill("200")
  await page.getByRole("spinbutton", { name: "Maximum points" }).fill("400")
  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)

  await page.getByRole("button", { name: "Reset", exact: true }).click()
  await page.keyboard.press("Escape")
  await page.getByLabel("Search server").fill("seed server group")
  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)

  await page.getByLabel("Search server").fill("")
  await page.getByLabel("Search server").fill("practice")
  await expect(page.getByText("kz_seed_gamma")).toBeVisible()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)

  await page.getByLabel("Search server").fill("")

  await page.getByRole("switch", { name: "Nub" }).click()

  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.getByText("kz_seed_beta")).toHaveCount(0)
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)

  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "SKZ" }).click()

  await expect(
    page.getByText(
      "No main stage pro records found for this player in the selected scope.",
    ),
  ).toBeVisible()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(0)

  expect(pbRequests).toEqual(
    expect.arrayContaining([
      {
        scope: "OVR",
        isProOnly: "false",
        stage: "0",
        steamid64,
      },
      {
        scope: "OVR",
        isProOnly: "true",
        stage: "0",
        steamid64,
      },
      {
        scope: "SKZ",
        isProOnly: "true",
        stage: "0",
        steamid64,
      },
    ]),
  )
})

test("Profile records points filter accepts typed minimum and maximum values", async ({
  page,
}) => {
  await installProfileShellRoutes(page)

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ovrRecords),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)
  await page.getByLabel("Filter by points range").click()

  const minimumPointsInput = page.getByRole("spinbutton", {
    name: "Minimum points",
  })
  const maximumPointsInput = page.getByRole("spinbutton", {
    name: "Maximum points",
  })

  await expect(minimumPointsInput).toHaveAttribute("type", "number")
  await expect(maximumPointsInput).toHaveAttribute("type", "number")

  await minimumPointsInput.fill("300")
  await maximumPointsInput.fill("400")

  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.getByText("kz_seed_beta")).toHaveCount(0)
  await expect(page.getByText("kz_seed_gamma")).toHaveCount(0)
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)
})

test("Profile records TP and rating filters accept typed ranges", async ({
  page,
}) => {
  await installProfileShellRoutes(page)

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ovrRecords),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)
  await page.getByLabel("Filter by TP range").click()

  const minimumTpInput = page.getByRole("spinbutton", {
    name: "Minimum TP",
  })
  const maximumTpInput = page.getByRole("spinbutton", {
    name: "Maximum TP",
  })

  await expect(minimumTpInput).not.toHaveAttribute("max")
  await expect(maximumTpInput).not.toHaveAttribute("max")
  await maximumTpInput.fill("1000000")
  await expect(maximumTpInput).toHaveValue("1000000")

  await minimumTpInput.fill("2")
  await maximumTpInput.fill("4")

  await expect(page.getByText("kz_seed_beta")).toBeVisible()
  await expect(page.getByText("kz_seed_alpha")).toHaveCount(0)
  await expect(page.getByText("kz_seed_gamma")).toHaveCount(0)

  await page.getByRole("button", { name: "Reset", exact: true }).click()
  await page.keyboard.press("Escape")
  await page.getByLabel("Filter by rating range").click()
  await page.getByRole("spinbutton", { name: "Minimum rating" }).fill("15")
  await page.getByRole("spinbutton", { name: "Maximum rating" }).fill("20")

  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.getByText("kz_seed_beta")).toHaveCount(0)
  await expect(page.getByText("kz_seed_gamma")).toHaveCount(0)
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)
})

test("Profile records time filter uses whole-second ranges", async ({
  page,
}) => {
  await installProfileShellRoutes(page)

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ count: 1, data: [seededPlayer] }),
    })
  })
  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ovrRecords),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)
  await page.getByLabel("Filter by time range").click()
  await page.getByRole("textbox", { name: "Minimum time" }).fill("0:50")
  await page.getByRole("textbox", { name: "Maximum time" }).fill("0:50")

  await expect(page.getByText("kz_seed_beta")).toBeVisible()
  await expect(page.getByText("kz_seed_alpha")).toHaveCount(0)
  await expect(page.getByText("kz_seed_gamma")).toHaveCount(0)
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)
})

test("Profile records date filter uses inclusive day precision", async ({
  page,
}) => {
  await installProfileShellRoutes(page)

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ovrRecords),
    })
  })

  await page.addInitScript(() => {
    if (!window.localStorage.getItem("gokz-datetime-format")) {
      window.localStorage.setItem("gokz-datetime-format", "iso")
    }
  })
  await page.goto(`/profile/${steamid64}/runs`)
  await page.getByLabel("Filter by date range").click()

  const fromDateInput = page.getByRole("textbox", {
    name: "From date",
    exact: true,
  })
  const toDateInput = page.getByRole("textbox", {
    name: "To date",
    exact: true,
  })

  await expect(fromDateInput).toHaveAttribute("type", "text")
  await expect(toDateInput).toHaveAttribute("type", "text")
  await expect(fromDateInput).toHaveAttribute("placeholder", "yyyy-mm-dd")
  await expect(toDateInput).toHaveAttribute("placeholder", "yyyy-mm-dd")
  await expect(page.getByLabel("Choose from date")).toHaveAttribute(
    "type",
    "date",
  )

  await fromDateInput.fill("20260330")
  await toDateInput.fill("20260331")
  await expect(fromDateInput).toHaveValue("2026-03-30")
  await expect(toDateInput).toHaveValue("2026-03-31")
  await toDateInput.press("Enter")

  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.getByText("kz_seed_beta")).toBeVisible()
  await expect(page.getByText("kz_seed_gamma")).toHaveCount(0)
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(2)

  await page.evaluate(() => {
    window.localStorage.setItem("gokz-datetime-format", "us")
  })
  await page.reload()
  await page.getByLabel("Filter by date range").click()
  await expect(
    page.getByRole("textbox", { name: "From date", exact: true }),
  ).toHaveAttribute("placeholder", "mm/dd/yyyy")
  await page
    .getByRole("textbox", { name: "From date", exact: true })
    .fill("03302026")
  await expect(
    page.getByRole("textbox", { name: "From date", exact: true }),
  ).toHaveValue("03/30/2026")

  await page.evaluate(() => {
    window.localStorage.setItem("gokz-datetime-format", "euro")
  })
  await page.reload()
  await page.getByLabel("Filter by date range").click()
  await expect(
    page.getByRole("textbox", { name: "From date", exact: true }),
  ).toHaveAttribute("placeholder", "dd/mm/yyyy")
  await page
    .getByRole("textbox", { name: "From date", exact: true })
    .fill("30032026")
  await expect(
    page.getByRole("textbox", { name: "From date", exact: true }),
  ).toHaveValue("30/03/2026")
})

test("Profile records presets persist and restore filters and sort", async ({
  page,
}) => {
  await installProfileShellRoutes(page)

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ovrRecords),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)
  await page.getByRole("switch", { name: "NUB" }).click()
  await page.getByLabel("Search map name").fill("alpha")
  await page.getByLabel("Filter by points range").click()
  await page.getByRole("spinbutton", { name: "Minimum points" }).fill("300")
  await page.getByRole("spinbutton", { name: "Maximum points" }).fill("400")
  await page.keyboard.press("Escape")
  await page.getByRole("button", { name: "Points", exact: true }).click()

  await page.getByRole("button", { name: "Presets" }).click()
  await page.getByText("Save current view").click()
  await expect(page.getByLabel("Preset name")).toHaveValue("Preset 1")
  await page.getByRole("button", { name: "Save preset" }).click()

  await page.getByRole("button", { name: "Presets" }).click()
  await page.getByText("Save current view").click()
  await expect(page.getByLabel("Preset name")).toHaveValue("Preset 2")
  await page.getByLabel("Preset name").fill("Focused PRO")
  await page.getByRole("button", { name: "Save preset" }).click()

  await expect
    .poll(() =>
      page.evaluate(() =>
        window.localStorage.getItem("gokz-profile-record-presets-v1"),
      ),
    )
    .toContain("Focused PRO")

  await page.getByRole("button", { name: "Presets" }).click()
  await page.getByText("Reset view").click()
  await expect(page.getByRole("switch", { name: "NUB" })).not.toBeChecked()
  await expect(page.getByLabel("Search map name")).toHaveValue("")

  await page.reload()
  await page.getByRole("button", { name: "Presets" }).click()
  await page.getByRole("button", { name: "Apply preset Focused PRO" }).click()

  await expect(page.getByRole("switch", { name: "PRO" })).toBeChecked()
  await expect(page.getByLabel("Search map name")).toHaveValue("alpha")
  await page.getByLabel("Filter by points range").click()
  await expect(
    page.getByRole("spinbutton", { name: "Minimum points" }),
  ).toHaveValue("300")
  await expect(
    page.getByRole("spinbutton", { name: "Maximum points" }),
  ).toHaveValue("400")
  await page.keyboard.press("Escape")
  await expect(
    page
      .getByRole("columnheader", { name: /Points/ })
      .locator(".lucide-arrow-down"),
  ).toBeVisible()

  await page.getByRole("button", { name: "Presets" }).click()
  await page.getByRole("button", { name: "Delete preset Focused PRO" }).click()
  await page.getByRole("button", { name: "Delete preset Preset 1" }).click()
  await expect(page.getByText("No saved presets yet.")).toBeVisible()
})

test("Profile records page shows grouped server links and filters by group name", async ({
  page,
}) => {
  await installProfileShellRoutes(page)

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ovrRecords),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)

  await expect(
    page.getByRole("link", { name: "Seed Server Group" }),
  ).toHaveAttribute("href", "/servers/group/seed-server-group")
  await expect(page.getByText("Seed Server", { exact: true })).toHaveCount(0)
  await expect(page.getByText("Second Server", { exact: true })).toBeVisible()
  const columns = await page
    .getByTestId("pb-records-table")
    .locator("thead tr")
    .first()
    .locator("th")
    .allTextContents()
  for (const name of ["Map", "Server"]) {
    const index = columns.findIndex((column) => column.trim() === name)
    expect(index).toBeGreaterThanOrEqual(0)
    await expect
      .poll(() =>
        page
          .getByTestId("pb-records-table")
          .locator("tbody tr")
          .first()
          .locator("td")
          .nth(index)
          .evaluate((cell) => cell.getBoundingClientRect().width),
      )
      .toBeLessThanOrEqual(241)
  }

  await page.getByLabel("Search server").fill("seed server group")
  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.getByText("kz_seed_beta")).toHaveCount(0)
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)
})

test("Profile records map tiles use the API preview when local images fail", async ({
  page,
}) => {
  await installProfileShellRoutes(page)
  await page.route("**/v1/maps/images/*.webp", (route) => route.abort())
  await page.route("**/v1/maps/preview-image?*", (route) =>
    route.fulfill({ contentType: "image/png", body: mapImagePixel }),
  )
  await page.route("**/v1/graphql", async (route) => {
    const body = route.request().postDataJSON() as { query?: string }
    if (body.query?.includes("query MapImages")) {
      await route.fulfill({
        status: 503,
        json: { errors: [{ message: "Image lookup unavailable" }] },
      })
      return
    }
    await route.fallback()
  })

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const recordType = url.searchParams.get("type")
    const isProOnly =
      url.searchParams.get("is_pro_only") ??
      (recordType === "PRO" ? "true" : recordType === "NUB" ? "false" : null)

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(isProOnly === "true" ? [ovrRecords[0]] : ovrRecords),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)

  const alphaMapTile = page
    .getByRole("link", { name: "kz_seed_alpha" })
    .locator("div")
    .first()
  await expect(alphaMapTile).toHaveAttribute(
    "style",
    /\/v1\/maps\/preview-image\?map_name=kz_seed_alpha/,
  )
})

test("Profile records map context menu items do not open run history", async ({
  page,
}) => {
  let runHistoryRequests = 0

  await installProfileShellRoutes(page)

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([ovrRecords[0]]),
    })
  })

  await page.route(/\/v1\/records\/run-history(\?.*)?$/, async (route) => {
    runHistoryRequests += 1
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0, wr_time: null }),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)

  await page.getByRole("link", { name: "kz_seed_alpha" }).click({
    button: "right",
  })
  await page.getByRole("menuitem", { name: "Copy Name" }).click()

  await expect(page.getByRole("menuitem", { name: "Copy Name" })).toHaveCount(0)
  await expect(page.getByTestId("record-run-history-dialog")).toHaveCount(0)
  await expect.poll(() => runHistoryRequests).toBe(0)
})

test("Profile record run history shows total records and playtime", async ({
  page,
}) => {
  await installProfileShellRoutes(page)

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([ovrRecords[0]]),
    })
  })

  await page.route(/\/v1\/records\/run-history(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 3,
        wr_time: 80,
        data: [
          {
            uuid: "019d1111-1111-7111-8111-111111111111",
            id: 981201,
            server_id: 980300,
            server_name: "Seed Server",
            mode_id: 200,
            mode: "KZT",
            time: 1500,
            teleports: 0,
            wr_gap: -2,
            is_pb: true,
            created_on: "2026-03-28T12:00:00Z",
            is_replay_available: false,
          },
          {
            uuid: "019d2222-2222-7222-8222-222222222222",
            id: 981202,
            server_id: 980300,
            server_name: "Seed Server",
            mode_id: 200,
            mode: "KZT",
            time: 1560,
            teleports: 2,
            wr_gap: -1.415,
            is_pb: false,
            created_on: "2026-03-29T12:00:00Z",
            is_replay_available: false,
          },
          {
            uuid: "019d3333-3333-7333-8333-333333333333",
            id: 981203,
            server_id: 980300,
            server_name: "Seed Server",
            mode_id: 201,
            mode: "SKZ",
            time: 1561.714,
            teleports: 0,
            wr_gap: -2.415,
            is_pb: true,
            created_on: "2026-03-30T12:00:00Z",
            is_replay_available: false,
          },
        ],
      }),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)

  const recordRow = page.getByTestId(`pb-record-row-${ovrRecords[0].uuid}`)
  await recordRow.focus()
  await page.keyboard.press("Enter")

  await expect(page.getByTestId("record-run-history-dialog")).toBeVisible()
  await expect(page.getByTestId("record-run-history-total-records")).toHaveText(
    "3",
  )
  await expect(
    page.getByTestId("record-run-history-total-playtime"),
  ).toHaveText("1.3 hours")

  await page.getByRole("tab", { name: "PB Runs" }).click()
  await expect(page.getByTestId("record-run-history-total-records")).toHaveText(
    "3",
  )
  await expect(
    page.getByTestId("record-run-history-total-playtime"),
  ).toHaveText("1.3 hours")
})

test("Profile records page shows an error state when PB loading fails", async ({
  page,
}) => {
  await installProfileShellRoutes(page)

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "boom" }),
    })
  })

  await page.goto(`/profile/${steamid64}/runs`)

  await expect(
    page.getByText(
      "Failed to load profile records. Reload the page and try again.",
    ),
  ).toBeVisible()
})

test("Legacy profile records URL redirects to the runs URL", async ({
  page,
}) => {
  await page.goto(`/profile/${steamid64}/records?scope=KZT`)

  await expect(page).toHaveURL(
    new RegExp(`/profile/${steamid64}/runs\\?scope=KZT$`),
  )
})

test("Profile ranks fetch only the visible page and never more than 50", async ({
  page,
}) => {
  await installProfileShellRoutes(page)
  await page.context().addCookies([
    {
      name: "profile_runs_show_ranks",
      value: "true",
      url: "http://localhost:5173",
    },
  ])
  await page.addInitScript(() =>
    localStorage.setItem("profile-runs-page-size", "100"),
  )
  const records = Array.from({ length: 125 }, (_, index) => ({
    ...ovrRecords[0],
    uuid: `019d7777-7777-7777-8777-${String(index).padStart(12, "0")}`,
    map_id: 980200 + index,
    map_name: `kz_rank_page_${String(index).padStart(3, "0")}`,
  }))
  await page.route(/\/v1\/records\/pb(\?.*)?$/, (route) => {
    expect(
      new URL(route.request().url()).searchParams.has("include_ranks"),
    ).toBe(false)
    return route.fulfill({ json: records })
  })
  const batches: string[][] = []
  await page.route(/\/v1\/records\/pb\/ranks\?/, async (route) => {
    const ids = new URL(route.request().url()).searchParams.getAll("uuid_list")
    batches.push(ids)
    expect(ids.length).toBeLessThanOrEqual(50)
    await route.fulfill({
      json: Object.fromEntries(ids.map((id, index) => [id, index + 1])),
    })
  })
  await page.goto(`/profile/${steamid64}/runs`)
  const rows = page.locator('[data-testid^="pb-record-row-"]')
  await expect(rows).toHaveCount(50)
  await expect(page.getByTestId("pb-record-rank").first()).toContainText("#")
  expect(batches).toHaveLength(1)
  const visibleIds = async () =>
    rows.evaluateAll((elements) =>
      elements
        .map((el) =>
          el.getAttribute("data-testid")!.replace("pb-record-row-", ""),
        )
        .sort(),
    )
  expect([...batches[0]].sort()).toEqual(await visibleIds())
  await page
    .getByRole("button", { name: "Go to next page", exact: true })
    .click()
  await expect.poll(() => batches.length).toBe(2)
  await expect(page.getByTestId("pb-record-rank").first()).toContainText("#")
  expect([...batches[1]].sort()).toEqual(await visibleIds())
  expect(batches[1].some((id) => batches[0].includes(id))).toBe(false)
  const secondPageIds = await visibleIds()
  await page.getByRole("button", { name: "Rank", exact: true }).click()
  expect(await visibleIds()).toEqual(secondPageIds)
  expect(batches).toHaveLength(2)
  await page
    .getByRole("button", { name: "Go to next page", exact: true })
    .click()
  await expect(rows).toHaveCount(25)
  await expect.poll(() => batches.length).toBe(3)
  expect(batches[2]).toHaveLength(25)
})

test("profile Runs default view persists until cleared", async ({ page }) => {
  await installProfileShellRoutes(page)
  await page.route(/\/v1\/records\/pb(\?.*)?$/, (route) =>
    route.fulfill({ json: ovrRecords }),
  )
  await page.goto(`/profile/${steamid64}/runs`)
  await page.getByRole("switch", { name: "NUB" }).click()
  await page.getByLabel("Search map name").fill("alpha")
  await page.getByRole("button", { name: "Points", exact: true }).click()
  await page.getByRole("button", { name: "Presets", exact: true }).click()
  await page
    .getByRole("menuitem", { name: "Set as default", exact: true })
    .click()
  await page.getByLabel("Search map name").fill("changed")
  await page.reload()
  await expect(page.getByRole("switch", { name: "PRO" })).toBeChecked()
  await expect(page.getByLabel("Search map name")).toHaveValue("alpha")
  await expect(
    page
      .getByRole("columnheader", { name: /Points/ })
      .locator(".lucide-arrow-down"),
  ).toBeVisible()
  await page.getByRole("button", { name: "Presets", exact: true }).click()
  await page
    .getByRole("menuitem", { name: "Clear default view", exact: true })
    .click()
  await page.reload()
  await expect(page.getByRole("switch", { name: "NUB" })).not.toBeChecked()
  await expect(page.getByLabel("Search map name")).toHaveValue("")
  await page.getByRole("button", { name: "Presets", exact: true }).click()
  await expect(
    page.getByRole("menuitem", { name: "Clear default view", exact: true }),
  ).toHaveCount(0)
})
