import { expect, type Page, type Route, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const steamid64 = "76561198000000123"

const player = {
  name: "Stats Runner",
  alias: "Stats Alias",
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2024-01-01T12:00:00Z",
  last_played_at: "2026-04-02T12:00:00Z",
  updated_at: "2026-04-02T12:00:00Z",
  steamid64,
  profile_views: 4,
}

const playerStats = {
  steamid64,
  daily_activity: null,
  playtime: {
    updated_at: "2026-04-03T12:00:00Z",
    total_seconds: 54000,
  },
  most_played_server: {
    updated_at: "2026-04-03T12:00:00Z",
    first_year: 2024,
    current_year: 2026,
    years: [2024, 2025, 2026],
    all_time: {
      total_seconds: 54000,
      entries: [
        {
          key: "group:11111111-1111-4111-8111-111111111111",
          label: "FemboyKZ | EU | Public | 128t VNL Global",
          total_seconds: 36000,
          server_count: 2,
          server_ids: [980300, 980301],
          group_id: "11111111-1111-4111-8111-111111111111",
        },
        {
          key: "server:980302",
          label: "Solo Climb Server",
          total_seconds: 18000,
          server_count: 1,
          server_ids: [980302],
        },
      ],
    },
    last_365_days: {
      total_seconds: 25200,
      entries: [
        {
          key: "group:11111111-1111-4111-8111-111111111111",
          label: "FemboyKZ | EU | Public | 128t VNL Global",
          total_seconds: 7200,
          server_count: 1,
          server_ids: [980301],
          group_id: "11111111-1111-4111-8111-111111111111",
        },
        {
          key: "server:980302",
          label: "Solo Climb Server",
          total_seconds: 18000,
          server_count: 1,
          server_ids: [980302],
        },
      ],
    },
    yearly: {
      "2024": {
        total_seconds: 10800,
        entries: [
          {
            key: "group:11111111-1111-4111-8111-111111111111",
            label: "FemboyKZ | EU | Public | 128t VNL Global",
            total_seconds: 10800,
            server_count: 1,
            server_ids: [980300],
            group_id: "11111111-1111-4111-8111-111111111111",
          },
        ],
      },
      "2025": {
        total_seconds: 18000,
        entries: [
          {
            key: "server:980302",
            label: "Solo Climb Server",
            total_seconds: 18000,
            server_count: 1,
            server_ids: [980302],
          },
        ],
      },
      "2026": {
        total_seconds: 25200,
        entries: [
          {
            key: "group:11111111-1111-4111-8111-111111111111",
            label: "FemboyKZ | EU | Public | 128t VNL Global",
            total_seconds: 25200,
            server_count: 2,
            server_ids: [980300, 980301],
            group_id: "11111111-1111-4111-8111-111111111111",
          },
        ],
      },
    },
  },
}

async function installProfileStatsRoutes(page: Page) {
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

  await page.route(/\/v1\/players\/[^/]+\/stats(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(playerStats),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/pinned-records(\?.*)?$/,
    async (route) => {
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

  await page.route(/\/v1\/players\/[^/]+\/social-links$/, async (route) => {
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

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  })

  await page.route(/\/v1\/records\/rank(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [],
        count: 0,
      }),
    })
  })

  await page.route(
    /\/v1\/leaderboards\/players\/[^?]+(\?.*)?$/,
    async (route) => {
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
          player: { steamid64, display_name: "Stats Alias" },
          scope: "OVR",
        }),
      })
    },
  )

  await page.route(/\/v1\/admin\/servers\/access$/, async (route) => {
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
}

test("Profile stats renders the most played server pie chart with timeline playback", async ({
  page,
}) => {
  await installProfileStatsRoutes(page)

  await page.goto(`/profile/${steamid64}/stats`)

  await expect(page).toHaveURL(new RegExp(`/profile/${steamid64}/stats$`))
  await expect(page.getByText("Most Played Server")).toBeVisible()
  await expect(page.getByTestId("profile-stats-view-all-time")).toBeVisible()
  await expect(
    page.getByTestId("profile-stats-view-last-365-days"),
  ).toBeVisible()
  await expect(page.getByTestId("profile-stats-view-2024")).toBeVisible()
  await expect(page.getByTestId("profile-stats-view-2025")).toBeVisible()
  await expect(page.getByTestId("profile-stats-view-2026")).toBeVisible()
  await expect(page.getByTestId("profile-stats-view-2024")).toHaveClass(
    /bg-card/,
  )
  expect(
    await page
      .locator('[data-testid^="profile-stats-view-"]')
      .evaluateAll((elements) =>
        elements.map((element) => element.textContent?.trim() ?? ""),
      ),
  ).toEqual(["2024", "2025", "2026", "Recent", "All time"])
  await expect(
    page.getByTestId("profile-stats-most-played-server-chart"),
  ).toBeVisible()
  await expect(
    page.getByTestId("profile-stats-most-played-server-chart"),
  ).toHaveAttribute("aria-label", /2024/)

  await page.getByTestId("profile-stats-view-all-time").click()
  await expect(
    page.getByTestId("profile-stats-most-played-server-chart"),
  ).toHaveAttribute("aria-label", /All time/)

  await page.getByTestId("profile-stats-playback-button").click()
  await expect(page.getByText("Pause")).toBeVisible()
  await page.waitForTimeout(1800)

  await expect(page.getByTestId("profile-stats-view-2024")).toHaveClass(
    /bg-card/,
  )
  await expect(
    page.getByTestId("profile-stats-most-played-server-chart"),
  ).toHaveAttribute("aria-label", /2024/)
})
