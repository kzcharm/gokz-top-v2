import { expect, type Page, test } from "@playwright/test"

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
  profile_views: 3,
}

async function installProfileShellRoutes(page: Page) {
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
    map_id: 980200,
    map_name: "kz_seed_alpha",
    map_tier: 4,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time: 42.123,
    teleports: 0,
    points: 350,
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
    map_tier: 6,
    mode_id: 201,
    mode: "SKZ",
    stage: 0,
    tickrate: 128,
    time: 50.456,
    teleports: 3,
    points: 510,
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
    map_tier: 2,
    mode_id: 202,
    mode: "NKZ",
    stage: 0,
    tickrate: 128,
    time: 61.234,
    teleports: 8,
    points: 120,
    created_on: "2026-03-29T12:00:00Z",
    updated_on: "2026-03-29T12:00:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
]

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

  await page.goto(`/profile/${steamid64}/records`)

  await expect(page.getByRole("link", { name: /Seed Alias/ })).toBeVisible()
  await expect(page.getByText("Skill radar")).toBeVisible()
  await expect(page.getByRole("tab", { name: "Records" })).toHaveAttribute(
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
  await expect(page.getByRole("columnheader", { name: "Server" })).toBeVisible()
  await expect(
    page.getByRole("columnheader", { name: "Datetime" }),
  ).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Player" })).toHaveCount(
    0,
  )

  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.getByText("kz_seed_beta")).toBeVisible()
  await expect(page.getByText("kz_seed_gamma")).toBeVisible()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(3)

  await expect(page.getByLabel("Search map name")).toBeVisible()
  await expect(page.getByLabel("Filter by mode")).toBeVisible()
  await expect(page.getByLabel("Filter by tier")).toBeVisible()
  await expect(page.getByLabel("Filter by points range")).toBeVisible()
  await expect(page.getByLabel("Search server")).toBeVisible()

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
  await page.getByLabel("Minimum points").fill("200")
  await page.getByLabel("Maximum points").fill("400")
  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)

  await page.getByRole("button", { name: "Reset" }).click()
  await page.keyboard.press("Escape")
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
      "No stage 0 pro records found for this player in the selected scope.",
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

  await page.goto(`/profile/${steamid64}/records`)

  await expect(
    page.getByText(
      "Failed to load profile records. Reload the page and try again.",
    ),
  ).toBeVisible()
})
