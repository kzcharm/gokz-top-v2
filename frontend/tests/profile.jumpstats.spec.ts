import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const steamid64 = "76561198000000001"

const seededPlayer = {
  name: "Seed Runner",
  alias: "Seed Alias",
  custom_id: null,
  avatar_hash: "seed-avatar-hash",
  country: "DE",
  created_at: "2026-03-01T12:00:00Z",
  last_played_at: "2026-03-31T12:00:00Z",
  updated_at: "2026-03-31T12:00:00Z",
  steamid64,
  profile_views: 3,
}

function buildPlayerRef(requestedSteamid64: string, displayName: string) {
  return {
    steamid64: requestedSteamid64,
    display_name: displayName,
    name: displayName,
    alias: displayName,
    custom_id: null,
    avatar_hash: "jumpstats-avatar-hash",
    country: "DE",
    primary_scope: "OVR",
    rating: 1500,
    is_website_user: false,
    last_played_at: "2026-03-31T12:00:00Z",
  }
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

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
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

test("Profile jumpstats refetches on jump type change and block toggle", async ({
  page,
}) => {
  const requests: Array<{
    type: string | null
    sortBy: string | null
    sortOrder: string | null
  }> = []

  await page.addInitScript(() => {
    localStorage.clear()
  })
  await installProfileShellRoutes(page)
  await page.route(/\/v1\/players\/[^/]+\/jumpstats(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const type = url.searchParams.get("type")
    const sortBy = url.searchParams.get("sort_by")
    const sortOrder = url.searchParams.get("sort_order")
    requests.push({ type, sortBy, sortOrder })

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [
          {
            id: "11111111-1111-4111-8111-111111111111",
            player: buildPlayerRef(steamid64, "Seed Alias"),
            server_group_id: "22222222-2222-4222-8222-222222222222",
            server_group: {
              id: "22222222-2222-4222-8222-222222222222",
              name: "Jumpstats Group",
            },
            mode: "KZT",
            type: type ?? "LJ",
            distance: sortBy === "block" ? 283.5 : 280.5,
            block: 282,
            strafes: 7,
            sync_percent: 88,
            pre_speed: 274.11,
            max_speed: 365.41,
            w_count: 0,
            overlap_count: 0,
            dead_air_count: 0,
            width: 18.5,
            height: 56.1,
            airtime_percent: 100,
            offset: 0,
            crouched_ticks: 0,
            edge: null,
            deviation: 3.25,
            jumped_at: "2099-01-01T00:00:00Z",
            created_at: "2099-01-01T00:00:00Z",
            updated_at: "2099-01-01T00:00:00Z",
          },
        ],
      }),
    })
  })

  await page.goto(`/profile/${steamid64}/jumpstats`)

  await expect(
    page.getByRole("tab", { name: "Long Jump", exact: true }),
  ).toHaveAttribute("data-state", "active")
  await expect(page.getByRole("columnheader", { name: "Block" })).toHaveCount(0)
  expect(requests[0]).toMatchObject({
    type: "LJ",
    sortBy: "distance",
    sortOrder: "desc",
  })

  await page.getByRole("tab", { name: "Bhop", exact: true }).click()
  expect(requests.some((request) => request.type === "BH")).toBe(true)

  await page.getByRole("button", { name: "Block" }).click()
  await expect(page.getByRole("columnheader", { name: "Block" })).toBeVisible()
  expect(
    requests.some(
      (request) => request.type === "BH" && request.sortBy === "block",
    ),
  ).toBe(true)

  await page.getByRole("button", { name: "Block" }).click()
  await expect(page.getByRole("columnheader", { name: "Block" })).toHaveCount(0)
})

test("Profile jumpstats rows open the shared details dialog", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.clear()
    let copiedText = ""
    Object.defineProperty(window, "__jumpstatCopiedText", {
      configurable: true,
      get: () => copiedText,
      set: (value: string) => {
        copiedText = value
      },
    })
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (text: string) => {
          copiedText = text
        },
      },
    })
  })
  await installProfileShellRoutes(page)
  await page.route(/\/v1\/players\/[^/]+\/jumpstats(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [
          {
            id: "11111111-1111-4111-8111-111111111111",
            player: buildPlayerRef(steamid64, "Seed Alias"),
            server_group_id: "22222222-2222-4222-8222-222222222222",
            server_group: {
              id: "22222222-2222-4222-8222-222222222222",
              name: "Jumpstats Group",
            },
            mode: "KZT",
            type: "LJ",
            distance: 281.1234,
            block: 280,
            strafes: 8,
            sync_percent: 90,
            pre_speed: 275.22,
            max_speed: 366.78,
            w_count: 1,
            overlap_count: 0,
            dead_air_count: 0,
            width: 18.5,
            height: 56.1,
            airtime_percent: 100,
            offset: 0,
            crouched_ticks: 0,
            edge: null,
            deviation: 3.25,
            jumped_at: "2099-01-01T00:00:00Z",
            created_at: "2099-01-01T00:00:00Z",
            updated_at: "2099-01-01T00:00:00Z",
          },
        ],
      }),
    })
  })
  await page.route(
    /\/v1\/jumpstats\/11111111-1111-4111-8111-111111111111$/,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "11111111-1111-4111-8111-111111111111",
          player: buildPlayerRef(steamid64, "Seed Alias"),
          server_group_id: "22222222-2222-4222-8222-222222222222",
          server_group: {
            id: "22222222-2222-4222-8222-222222222222",
            name: "Jumpstats Group",
          },
          mode: "KZT",
          type: "LJ",
          distance: 281.1234,
          block: 280,
          strafes: 8,
          sync_percent: 90,
          pre_speed: 275.22,
          max_speed: 366.78,
          w_count: 1,
          overlap_count: 0,
          dead_air_count: 0,
          width: 18.5,
          height: 56.1,
          airtime_percent: 100,
          offset: 0,
          crouched_ticks: 0,
          edge: null,
          deviation: 3.25,
          jumped_at: "2099-01-01T00:00:00Z",
          created_at: "2099-01-01T00:00:00Z",
          updated_at: "2099-01-01T00:00:00Z",
          strafe_stats: [
            {
              index: 1,
              sync_percent: 90,
              gain: 10,
              loss: 0,
              airtime_percent: 50,
              width: 12,
              overlap_count: 0,
              dead_air_count: 0,
            },
          ],
        }),
      })
    },
  )
  await page.route(
    /\/v1\/jumpstats\/11111111-1111-4111-8111-111111111111\/visualization$/,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          version: 1,
          jump_direction: "FORWARDS",
          deviation_angle: -12.5,
          bounds: {
            min_x: -1,
            max_x: 1,
            min_y: 0,
            max_y: 3,
          },
          samples: [
            {
              index: 0,
              x: 0,
              y: 0,
              yaw_delta: 0,
              mouse_direction: "NONE",
              a_pressed: false,
              d_pressed: false,
              strafe_type: "NONE",
            },
            {
              index: 1,
              x: 0.2,
              y: 2.5,
              yaw_delta: 8,
              mouse_direction: "RIGHT",
              a_pressed: false,
              d_pressed: true,
              strafe_type: "RIGHT",
            },
          ],
        }),
      })
    },
  )

  await page.goto(`/profile/${steamid64}/jumpstats`)

  const detailResponsePromise = page.waitForResponse(
    /\/v1\/jumpstats\/11111111-1111-4111-8111-111111111111$/,
  )
  const visualizationResponsePromise = page.waitForResponse(
    /\/v1\/jumpstats\/11111111-1111-4111-8111-111111111111\/visualization$/,
  )
  await page.locator("tbody tr").first().click()
  await detailResponsePromise
  await visualizationResponsePromise

  await expect(page.getByRole("dialog")).toBeVisible()
  await expect(page.getByRole("dialog")).toContainText(
    "Seed Alias jumped 281.1234 units with a Long Jump",
  )
  await expect(
    page.getByRole("img", { name: "Route visualization" }),
  ).toBeVisible()
  await expect(page.getByRole("dialog")).toContainText(
    "Deviation angle: -12.50°",
  )
})
