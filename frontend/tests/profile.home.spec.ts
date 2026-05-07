import { expect, type Page, type Route, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const steamid64 = "76561198000000001"

const player = {
  name: "Pinned Runner",
  alias: "Pinned Alias",
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2026-03-01T12:00:00Z",
  last_played_at: "2026-03-31T12:00:00Z",
  updated_at: "2026-03-31T12:00:00Z",
  steamid64,
  profile_views: 7,
}

const playerStats = {
  steamid64,
  daily_activity: {
    updated_at: "2026-04-03T12:00:00Z",
    days: [
      { date: "2025-12-31", count: 2 },
      { date: "2026-01-01", count: 1 },
      { date: "2026-03-30", count: 2 },
      { date: "2026-03-31", count: 4 },
    ],
  },
  playtime: {
    updated_at: "2026-04-03T12:00:00Z",
    total_seconds: 37800,
  },
}

function createAccessToken(targetSteamid64: string) {
  const header = Buffer.from(
    JSON.stringify({ alg: "none", typ: "JWT" }),
  ).toString("base64url")
  const payload = Buffer.from(
    JSON.stringify({ sub: targetSteamid64 }),
  ).toString("base64url")
  return `${header}.${payload}.signature`
}

const nubRecords = [
  {
    uuid: "019d1111-1111-7111-8111-111111111111",
    id: 981200,
    player: { steamid64, display_name: "Pinned Alias" },
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: 980200,
    map_name: "kz_alpha",
    map_tier: 4,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time: 42.123,
    teleports: 1,
    points: 960,
    created_on: "2026-03-31T12:00:00Z",
    updated_on: "2026-03-31T12:00:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
  {
    uuid: "019d2222-2222-7222-8222-222222222222",
    id: 981201,
    player: { steamid64, display_name: "Pinned Alias" },
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: 980201,
    map_name: "kz_beta",
    map_tier: 5,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time: 43.5,
    teleports: 2,
    points: 920,
    created_on: "2026-03-30T08:15:00Z",
    updated_on: "2026-03-30T08:15:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
  {
    uuid: "019d3333-3333-7333-8333-333333333333",
    id: 981202,
    player: { steamid64, display_name: "Pinned Alias" },
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: 980202,
    map_name: "kz_gamma",
    map_tier: 2,
    mode_id: 201,
    mode: "SKZ",
    stage: 0,
    tickrate: 128,
    time: 39.25,
    teleports: 4,
    points: 920,
    created_on: "2026-03-29T09:00:00Z",
    updated_on: "2026-03-29T09:00:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
  {
    uuid: "019d4444-4444-7444-8444-444444444444",
    id: 981203,
    player: { steamid64, display_name: "Pinned Alias" },
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: 980203,
    map_name: "kz_delta",
    map_tier: 6,
    mode_id: 202,
    mode: "VNL",
    stage: 0,
    tickrate: 128,
    time: 50.1,
    teleports: 6,
    points: 850,
    created_on: "2026-03-28T10:00:00Z",
    updated_on: "2026-03-28T10:00:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
  {
    uuid: "019d5555-5555-7555-8555-555555555555",
    id: 981204,
    player: { steamid64, display_name: "Pinned Alias" },
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: 980204,
    map_name: "kz_epsilon",
    map_tier: 1,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time: 38.999,
    teleports: 3,
    points: 810,
    created_on: "2026-03-27T11:30:00Z",
    updated_on: "2026-03-27T11:30:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
  {
    uuid: "019d6666-6666-7666-8666-666666666666",
    id: 981205,
    player: { steamid64, display_name: "Pinned Alias" },
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: 980205,
    map_name: "kz_zeta",
    map_tier: 7,
    mode_id: 203,
    mode: "NKZ",
    stage: 0,
    tickrate: 128,
    time: 55.75,
    teleports: 7,
    points: 790,
    created_on: "2026-03-26T14:45:00Z",
    updated_on: "2026-03-26T14:45:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
  {
    uuid: "019d7777-7777-7777-8777-777777777777",
    id: 981206,
    player: { steamid64, display_name: "Pinned Alias" },
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: 980206,
    map_name: "kz_hidden_bonus",
    map_tier: 3,
    mode_id: 200,
    mode: "KZT",
    stage: 1,
    tickrate: 128,
    time: 20.0,
    teleports: 0,
    points: 999,
    created_on: "2026-03-25T12:00:00Z",
    updated_on: "2026-03-25T12:00:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
]

async function installProfileHomeRoutes(
  page: Page,
  {
    stats = playerStats,
    currentUserSteamid64 = null,
    activeBans = [],
  }: {
    stats?: typeof playerStats
    currentUserSteamid64?: string | null
    activeBans?: Array<{
      id: number
      ban_type: string
      created_on: string
      expires_on?: string | null
      notes?: string | null
    }>
  } = {},
) {
  const requestedRankUuids: string[] = []
  let unbanCheckCalls = 0
  let activeBanState = [...activeBans]
  const pinnedRecords = nubRecords.slice(0, 6).map((record, index) => ({
    id: `019e0000-0000-7000-8000-00000000000${index}`,
    player_steamid64: steamid64,
    map_id: record.map_id,
    scope: "OVR",
    type: "NUB",
    record,
  }))

  if (currentUserSteamid64) {
    await page.addInitScript((token) => {
      localStorage.setItem("access_token", token)
    }, createAccessToken(currentUserSteamid64))
  }

  await page.route(/\/v1\/users\/me$/, async (route: Route) => {
    if (currentUserSteamid64) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          steamid64: currentUserSteamid64,
          is_active: true,
          roles: [],
          created_at: "2026-03-01T12:00:00Z",
          last_visited_at: "2026-04-01T12:00:00Z",
          player: {
            steamid64: currentUserSteamid64,
            display_name:
              currentUserSteamid64 === steamid64
                ? player.alias
                : "Other Viewer",
          },
        }),
      })
      return
    }

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

  await page.route(/\/v1\/bans(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: activeBanState,
        count: activeBanState.length,
      }),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/unban-check$/,
    async (route: Route) => {
      unbanCheckCalls += 1
      const clearedBanCount = activeBanState.length
      activeBanState = []

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          message:
            "Your ban status has been updated and no active bans remain.",
          cleared_ban_count: clearedBanCount,
          remaining_active_ban_count: activeBanState.length,
        }),
      })
    },
  )

  await page.route(/\/v1\/maps(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/pinned-records(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: pinnedRecords,
          count: pinnedRecords.length,
        }),
      })
    },
  )

  await page.route(
    /\/v1\/players\/[^/]+\/social-links$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [
            {
              id: "019e0000-0000-7000-8000-000000000101",
              player_steamid64: steamid64,
              platform: "github",
              account_identifier: "pinned-alias",
              verified: false,
              url: "https://github.com/pinned-alias",
              created_at: "2026-04-01T00:00:00Z",
              updated_at: "2026-04-01T00:00:00Z",
            },
          ],
          count: 1,
        }),
      })
    },
  )

  await page.route(
    /\/v1\/players\/[^/]+\/stats(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(stats),
      })
    },
  )

  await page.route(/\/v1\/admin\/servers\/access$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        role: "server_owner",
        can_approve_servers: false,
        owned_group_count: 0,
      }),
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
          rating_easy: 0,
          rating_hard: 0,
          points: 0,
          wrs_nub: 0,
          wrs_pro: 0,
          records_900_plus: 0,
          records_800_plus: 0,
          unique_map_finishes: 0,
          player: { steamid64, display_name: "Pinned Alias" },
          scope: "OVR",
        }),
      })
    },
  )

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url())
    const type = url.searchParams.get("type")

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(type === "PRO" ? [] : nubRecords),
    })
  })

  await page.route(/\/v1\/records\/rank(\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url())
    requestedRankUuids.push(...url.searchParams.getAll("uuid_list"))

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          { record_uuid: nubRecords[0].uuid, rank: 1 },
          { record_uuid: nubRecords[2].uuid, rank: 2 },
          { record_uuid: nubRecords[1].uuid, rank: 3 },
          { record_uuid: nubRecords[3].uuid, rank: 8 },
          { record_uuid: nubRecords[4].uuid, rank: 11 },
          { record_uuid: nubRecords[5].uuid, rank: null },
        ],
        count: 6,
      }),
    })
  })

  return {
    requestedRankUuids,
    getUnbanCheckCalls: () => unbanCheckCalls,
  }
}

test("Profile home renders live pinned records with points badges and absolute dates", async ({
  page,
}) => {
  const { requestedRankUuids } = await installProfileHomeRoutes(page)

  await page.goto(`/profile/${steamid64}`)

  await expect(page.getByText("Pinned Alias")).toBeVisible()
  await expect(page.getByText(/^Mon$/)).toBeVisible()
  await expect(page.getByText(/^Wed$/)).toBeVisible()
  await expect(page.getByText(/^Fri$/)).toBeVisible()
  await expect(page.getByText(/^Jan$/)).toBeVisible()
  await expect(page.getByText(/^Mar$/)).toBeVisible()
  await expect(page.getByText("10.5 hrs")).toBeVisible()
  await expect(page.getByText("Latest", { exact: true })).toBeVisible()
  await expect(
    page.getByTestId("profile-activity-view-last-365-days"),
  ).toBeVisible()
  await expect(page.getByTestId("profile-activity-view-2026")).toBeVisible()
  await expect(page.getByTestId("profile-activity-view-2025")).toBeVisible()
  await expect(
    page.getByTestId("profile-activity-view-last-365-days"),
  ).toHaveClass(/bg-card/)
  await expect(page.getByTestId("profile-activity-view-2026")).not.toHaveClass(
    /bg-card/,
  )
  await expect(
    page.getByTestId("profile-activity-cell-2026-03-31"),
  ).toHaveAttribute("data-activity-level", "2")
  await expect(
    page.getByTestId("profile-activity-cell-2026-03-30"),
  ).toHaveAttribute("data-activity-level", "2")
  await expect(
    page.getByTestId("profile-activity-cell-2026-01-01"),
  ).toHaveAttribute("data-activity-level", "1")
  await expect(
    page.getByTestId("profile-activity-cell-2025-12-31"),
  ).toHaveAttribute("data-activity-level", "2")

  await page.getByTestId("profile-activity-view-2025").click()
  await expect(
    page.getByTestId("profile-activity-cell-2025-12-31"),
  ).toHaveAttribute("data-activity-level", "2")

  await expect(page.getByText("Pinned records")).toBeVisible()
  await expect(page.getByText("6 of 6")).toBeVisible()

  await expect(page.getByText("kz_alpha")).toBeVisible()
  await expect(page.getByText("kz_beta")).toBeVisible()
  await expect(page.getByText("kz_gamma")).toBeVisible()
  await expect(page.getByText("kz_delta")).toBeVisible()
  await expect(page.getByText("kz_epsilon")).toBeVisible()
  await expect(page.getByText("kz_zeta")).toBeVisible()
  await expect(page.getByText("kz_hidden_bonus")).toHaveCount(0)

  await expect(page.getByText("WR", { exact: true })).toHaveCount(0)
  await expect(page.getByText("Top 10", { exact: true })).toHaveCount(0)
  await expect(page.getByText("960")).toBeVisible()
  await expect(page.getByText("920")).toHaveCount(2)

  await expect(page.getByText(/^KZT · #1$/)).toBeVisible()
  await expect(page.getByText(/^SKZ · #2$/)).toBeVisible()
  await expect(page.getByText(/^KZT · #3$/)).toBeVisible()
  await expect(page.getByText(/^NKZ · Rank unavailable$/)).toBeVisible()

  await expect(page.getByText(/^2026-03-31 \d{2}:00$/)).toBeVisible()
  await expect(page.getByText(/^2026-03-30 \d{2}:15$/)).toBeVisible()

  expect(requestedRankUuids).toEqual([
    nubRecords[0].uuid,
    nubRecords[1].uuid,
    nubRecords[2].uuid,
    nubRecords[3].uuid,
    nubRecords[4].uuid,
    nubRecords[5].uuid,
  ])
})

test("Profile card renders unverified social link icons", async ({ page }) => {
  await installProfileHomeRoutes(page)

  await page.goto(`/profile/${steamid64}`)

  await expect(page.getByTestId("profile-social-links")).toBeVisible()
  await expect(page.getByTestId("profile-social-link-github")).toHaveAttribute(
    "href",
    "https://github.com/pinned-alias",
  )
  await expect(
    page.getByLabel("GitHub unverified link for Pinned Alias"),
  ).toBeVisible()
})

test("Profile home activity card shows empty-year message for players without activity", async ({
  page,
}) => {
  await installProfileHomeRoutes(page, {
    stats: {
      steamid64,
      daily_activity: {
        updated_at: "2026-04-03T12:00:00Z",
        days: [],
      },
      playtime: {
        updated_at: "2026-04-03T12:00:00Z",
        total_seconds: 0,
      },
    },
  })

  await page.goto(`/profile/${steamid64}`)

  await expect(
    page.getByTestId("profile-activity-view-last-365-days"),
  ).toBeVisible()
  await expect(
    page.getByText("No record submissions found in the latest 365 days."),
  ).toBeVisible()
  await expect(
    page.getByTestId(/profile-activity-cell-.*-empty-0-0/),
  ).toHaveAttribute("data-activity-level", "0")
})

test("Own profile can check GlobalAPI unban status and clear the ban warning", async ({
  page,
}) => {
  const { getUnbanCheckCalls } = await installProfileHomeRoutes(page, {
    currentUserSteamid64: steamid64,
    activeBans: [
      {
        id: 2001,
        ban_type: "bhop_hack",
        created_on: "2026-04-01T12:00:00Z",
        expires_on: null,
        notes: "Permanent local mirror",
      },
    ],
  })

  await page.goto(`/profile/${steamid64}`)

  await expect(page.getByText("This player has been banned")).toBeVisible()
  await expect(page.getByTestId("profile-unban-check-button")).toBeVisible()

  await page.getByTestId("profile-unban-check-button").click()

  await expect(page.getByText("This player has been banned")).toHaveCount(0)
  expect(getUnbanCheckCalls()).toBe(1)
})

test("Other viewers do not see the unban check button", async ({ page }) => {
  await installProfileHomeRoutes(page, {
    currentUserSteamid64: "76561198000000099",
    activeBans: [
      {
        id: 2002,
        ban_type: "bhop_hack",
        created_on: "2026-04-01T12:00:00Z",
        expires_on: null,
        notes: "Permanent local mirror",
      },
    ],
  })

  await page.goto(`/profile/${steamid64}`)

  await expect(page.getByText("This player has been banned")).toBeVisible()
  await expect(page.getByTestId("profile-unban-check-button")).toHaveCount(0)
})
