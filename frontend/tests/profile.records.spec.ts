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
    /\/v1\/maps\/preview-image\?map_name=kz_seed_alpha/,
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

  await page.getByLabel("Search server").fill("seed server group")
  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.getByText("kz_seed_beta")).toHaveCount(0)
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)
})

test("Profile records map tiles include API preview fallback URLs", async ({
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
    /github\.com\/KZGlobalTeam\/map-images\/raw\/public\/webp\/kz_seed_alpha\.webp/,
  )
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
