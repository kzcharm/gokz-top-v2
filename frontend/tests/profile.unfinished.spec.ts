import { expect, type Page, type Route, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const steamid64 = "76561198000000001"

const player = {
  name: "Unfinished Runner",
  alias: "Unfinished Alias",
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2026-03-01T12:00:00Z",
  last_played_at: "2026-03-31T12:00:00Z",
  updated_at: "2026-03-31T12:00:00Z",
  steamid64,
  profile_views: 7,
}

const validatedMaps = [
  {
    id: 980200,
    name: "kz_alpha",
    filesize: 123,
    validated: true,
    tiers: { OVR: 3, KZT: 3, SKZ: 2, VNL: 1 },
    created_on: "2026-01-01T00:00:00Z",
    updated_on: "2026-01-02T00:00:00Z",
    approved_by_steamid64: steamid64,
    workshop_id: null,
    synced_at: "2026-03-31T00:00:00Z",
    authors: [],
    no_steamid_names: [],
    review_summary: null,
  },
  {
    id: 980201,
    name: "kz_beta",
    filesize: 123,
    validated: true,
    tiers: { OVR: 5, KZT: 5, SKZ: 0, VNL: 0 },
    created_on: "2026-01-01T00:00:00Z",
    updated_on: "2026-01-02T00:00:00Z",
    approved_by_steamid64: steamid64,
    workshop_id: null,
    synced_at: "2026-03-31T00:00:00Z",
    authors: [],
    no_steamid_names: [],
    review_summary: null,
  },
  {
    id: 980202,
    name: "kz_gamma",
    filesize: 123,
    validated: true,
    tiers: { OVR: 4, KZT: 0, SKZ: 6, VNL: 0 },
    created_on: "2026-01-01T00:00:00Z",
    updated_on: "2026-01-02T00:00:00Z",
    approved_by_steamid64: steamid64,
    workshop_id: null,
    synced_at: "2026-03-31T00:00:00Z",
    authors: [],
    no_steamid_names: [],
    review_summary: null,
  },
  {
    id: 980203,
    name: "kz_delta",
    filesize: 123,
    validated: true,
    tiers: { OVR: 2, KZT: 2, SKZ: 1, VNL: 0 },
    created_on: "2026-01-01T00:00:00Z",
    updated_on: "2026-01-02T00:00:00Z",
    approved_by_steamid64: steamid64,
    workshop_id: null,
    synced_at: "2026-03-31T00:00:00Z",
    authors: [],
    no_steamid_names: [],
    review_summary: null,
  },
  {
    id: 980204,
    name: "kz_epsilon",
    filesize: 123,
    validated: true,
    tiers: { OVR: 0, KZT: 0, SKZ: 4, VNL: 0 },
    created_on: "2026-01-01T00:00:00Z",
    updated_on: "2026-01-02T00:00:00Z",
    approved_by_steamid64: steamid64,
    workshop_id: null,
    synced_at: "2026-03-31T00:00:00Z",
    authors: [],
    no_steamid_names: [],
    review_summary: null,
  },
]

function buildRecord({
  uuid,
  mapId,
  mapName,
  mapTier,
  mode,
  modeId = 200,
}: {
  uuid: string
  mapId: number
  mapName: string
  mapTier: number
  mode: string
  modeId?: number
}) {
  return {
    uuid,
    id: null,
    player: { steamid64, display_name: player.alias },
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: mapId,
    map_name: mapName,
    map_tier: mapTier,
    mode_id: modeId,
    mode,
    stage: 0,
    tickrate: 128,
    time: 42.123,
    teleports: 1,
    points: 800,
    created_on: "2026-03-31T12:00:00Z",
    updated_on: "2026-03-31T12:00:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  }
}

const pbRecordsByScopeAndType = {
  OVR: {
    NUB: [
      buildRecord({
        uuid: "019d0000-0000-7000-8000-000000000001",
        mapId: 980200,
        mapName: "kz_alpha",
        mapTier: 3,
        mode: "KZT",
      }),
    ],
    PRO: [
      buildRecord({
        uuid: "019d0000-0000-7000-8000-000000000011",
        mapId: 980200,
        mapName: "kz_alpha",
        mapTier: 3,
        mode: "KZT",
      }),
      buildRecord({
        uuid: "019d0000-0000-7000-8000-000000000012",
        mapId: 980201,
        mapName: "kz_beta",
        mapTier: 5,
        mode: "KZT",
      }),
    ],
  },
  SKZ: {
    NUB: [
      buildRecord({
        uuid: "019d0000-0000-7000-8000-000000000021",
        mapId: 980202,
        mapName: "kz_gamma",
        mapTier: 6,
        mode: "SKZ",
        modeId: 201,
      }),
    ],
    PRO: [],
  },
  VNL: {
    NUB: [
      buildRecord({
        uuid: "019d0000-0000-7000-8000-000000000031",
        mapId: 980200,
        mapName: "kz_alpha",
        mapTier: 1,
        mode: "VNL",
        modeId: 202,
      }),
    ],
    PRO: [
      buildRecord({
        uuid: "019d0000-0000-7000-8000-000000000032",
        mapId: 980200,
        mapName: "kz_alpha",
        mapTier: 1,
        mode: "VNL",
        modeId: 202,
      }),
    ],
  },
} as const

const wrsByScopeAndType = {
  OVR: {
    NUB: [
      {
        record_uuid: "019d1000-0000-7000-8000-000000000001",
        map_id: 980201,
        scope: "OVR",
        type: "NUB",
        mode_id: 200,
        player: { steamid64: "76561198000000999", display_name: "WR Holder" },
        time: 45.111,
        updated_at: "2026-03-31T12:00:00Z",
      },
      {
        record_uuid: "019d1000-0000-7000-8000-000000000002",
        map_id: 980202,
        scope: "OVR",
        type: "NUB",
        mode_id: 201,
        player: { steamid64: "76561198000000998", display_name: "WR Holder 2" },
        time: 55.222,
        updated_at: "2026-03-31T12:00:00Z",
      },
    ],
    PRO: [
      {
        record_uuid: "019d1000-0000-7000-8000-000000000011",
        map_id: 980202,
        scope: "OVR",
        type: "PRO",
        mode_id: 201,
        player: { steamid64: "76561198000000997", display_name: "WR Holder 3" },
        time: 48.333,
        updated_at: "2026-03-31T12:00:00Z",
      },
      {
        record_uuid: "019d1000-0000-7000-8000-000000000012",
        map_id: 980203,
        scope: "OVR",
        type: "PRO",
        mode_id: 200,
        player: { steamid64: "76561198000000996", display_name: "WR Holder 4" },
        time: 60.444,
        updated_at: "2026-03-31T12:00:00Z",
      },
    ],
  },
  SKZ: {
    NUB: [
      {
        record_uuid: "019d1000-0000-7000-8000-000000000021",
        map_id: 980200,
        scope: "SKZ",
        type: "NUB",
        mode_id: 201,
        player: { steamid64: "76561198000000995", display_name: "WR Holder 5" },
        time: 40.5,
        updated_at: "2026-03-31T12:00:00Z",
      },
      {
        record_uuid: "019d1000-0000-7000-8000-000000000022",
        map_id: 980204,
        scope: "SKZ",
        type: "NUB",
        mode_id: 201,
        player: { steamid64: "76561198000000994", display_name: "WR Holder 6" },
        time: 70,
        updated_at: "2026-03-31T12:00:00Z",
      },
    ],
    PRO: [],
  },
  VNL: {
    NUB: [
      {
        record_uuid: "019d1000-0000-7000-8000-000000000031",
        map_id: 980200,
        scope: "VNL",
        type: "NUB",
        mode_id: 202,
        player: { steamid64: "76561198000000993", display_name: "WR Holder 7" },
        time: 33.333,
        updated_at: "2026-03-31T12:00:00Z",
      },
    ],
    PRO: [],
  },
} as const

async function installProfileRoutes(page: Page) {
  await page.route(/\/v1\/users\/me$/, async (route: Route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Unauthorized" }),
    })
  })

  await page.route(/\/v1\/players\/[^/]+$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(player),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/follow-summary$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          follower_count: 2,
          following_count: 3,
          viewer_is_following: null,
          viewer_is_self: false,
        }),
      })
    },
  )

  await page.route(
    /\/v1\/players\/[^/]+\/pinned-records(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [],
          count: 0,
        }),
      })
    },
  )

  await page.route(/\/v1\/bans(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })

  await page.route(/\/v1\/maps\/wrs(\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url())
    const scope = (url.searchParams.get("scope") ??
      "OVR") as keyof typeof wrsByScopeAndType
    const type = (url.searchParams.get("type") ?? "NUB") as "NUB" | "PRO"

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(wrsByScopeAndType[scope][type]),
    })
  })

  await page.route(/\/v1\/maps(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(validatedMaps),
    })
  })

  await page.route(
    /\/v1\/leaderboards\/players\/[^?]+(\?.*)?$/,
    async (route: Route) => {
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

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url())
    const scope = (url.searchParams.get("scope") ??
      "OVR") as keyof typeof pbRecordsByScopeAndType
    const type = (url.searchParams.get("type") ?? "NUB") as "NUB" | "PRO"

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(pbRecordsByScopeAndType[scope][type]),
    })
  })
}

async function expectRowOrder(
  page: Page,
  type: "nub" | "pro",
  mapNames: string[],
) {
  const rows = page.locator(`[data-testid^="profile-unfinished-${type}-row-"]`)
  await expect(rows).toHaveCount(mapNames.length)

  for (const [index, mapName] of mapNames.entries()) {
    await expect(rows.nth(index)).toContainText(mapName)
  }
}

test("Profile unfinished tab shows NUB and PRO side by side when width allows", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  await installProfileRoutes(page)

  await page.goto(`/profile/${steamid64}/unfinished`)

  await expect(page.getByRole("tab", { name: "Unfinished" })).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`/profile/${steamid64}/unfinished$`))
  await expect(page.getByLabel("Search unfinished map name")).toBeVisible()
  await expect(page.getByLabel("Filter unfinished maps by tier")).toBeVisible()
  await expect(page.getByTestId("profile-unfinished-column-nub")).toBeVisible()
  await expect(page.getByTestId("profile-unfinished-column-pro")).toBeVisible()
  await expect(page.getByRole("switch")).toHaveCount(0)
  await expect(
    page
      .getByTestId("profile-unfinished-column-nub")
      .getByRole("columnheader", { name: "Map" }),
  ).toBeVisible()
  await expect(
    page
      .getByTestId("profile-unfinished-column-pro")
      .getByRole("columnheader", { name: "WR Time" }),
  ).toBeVisible()

  await expectRowOrder(page, "nub", ["kz_beta", "kz_delta", "kz_gamma"])
  await expectRowOrder(page, "pro", ["kz_delta", "kz_gamma"])
  await expect(page.getByText("45.111")).toBeVisible()
  await expect(page.getByText("55.222")).toBeVisible()
  await expect(
    page.locator('[data-testid="profile-unfinished-nub-row-980203"]'),
  ).toContainText("-")
  await expect(
    page.getByTestId("profile-unfinished-nub-row-980200"),
  ).toHaveCount(0)
  await expect(
    page.getByTestId("profile-unfinished-nub-row-980204"),
  ).toHaveCount(0)

  await page.getByLabel("Search unfinished map name").fill("gam")
  await expectRowOrder(page, "nub", ["kz_gamma"])
  await expectRowOrder(page, "pro", ["kz_gamma"])
  await page.getByLabel("Search unfinished map name").fill("")

  await page.getByLabel("Filter unfinished maps by tier").click()
  await page.getByRole("option", { name: "T2" }).click()
  await expectRowOrder(page, "nub", ["kz_delta"])
  await expectRowOrder(page, "pro", ["kz_delta"])
  await page.getByLabel("Filter unfinished maps by tier").click()
  await page.getByRole("option", { name: "Tier" }).click()

  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "SKZ" }).click()

  await expectRowOrder(page, "nub", ["kz_alpha", "kz_delta", "kz_epsilon"])
  await expectRowOrder(page, "pro", [
    "kz_alpha",
    "kz_delta",
    "kz_epsilon",
    "kz_gamma",
  ])
  await expect(page.getByText("1:10.000")).toBeVisible()
  await expect(
    page.getByTestId("profile-unfinished-nub-row-980202"),
  ).toHaveCount(0)
  await expect(
    page.getByTestId("profile-unfinished-nub-row-980201"),
  ).toHaveCount(0)

  await page
    .getByTestId("profile-unfinished-column-nub")
    .getByRole("button", { name: "WR Time" })
    .click()
  await expectRowOrder(page, "nub", ["kz_epsilon", "kz_alpha", "kz_delta"])
  await expectRowOrder(page, "pro", [
    "kz_alpha",
    "kz_delta",
    "kz_epsilon",
    "kz_gamma",
  ])
})

test("Profile unfinished tab keeps the NUB PRO switch on mobile widths", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await installProfileRoutes(page)

  await page.goto(`/profile/${steamid64}/unfinished`)

  await expect(page.getByRole("switch")).toBeVisible()
  await expect(page.getByTestId("profile-unfinished-column-nub")).toBeVisible()
  await expect(page.getByTestId("profile-unfinished-column-pro")).toHaveCount(0)

  await expectRowOrder(page, "nub", ["kz_beta", "kz_delta", "kz_gamma"])
  await page.getByRole("switch").click()
  await expect(page.getByTestId("profile-unfinished-column-pro")).toBeVisible()
  await expectRowOrder(page, "pro", ["kz_delta", "kz_gamma"])
})

test("Profile unfinished tab shows an empty state when the scope has no missing maps", async ({
  page,
}) => {
  await installProfileRoutes(page)
  await page.addInitScript(() => {
    localStorage.setItem("gokz-app-scope", "VNL")
  })

  await page.goto(`/profile/${steamid64}/unfinished`)
  await expect(
    page.getByText(
      "No unfinished maps found for this player in the selected scope.",
    ),
  ).toBeVisible()
  await expect(
    page.locator('[data-testid^="profile-unfinished-nub-row-"]'),
  ).toHaveCount(0)
  await expect(
    page.locator('[data-testid^="profile-unfinished-pro-row-"]'),
  ).toHaveCount(0)
})
