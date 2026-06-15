import { expect, type Page, type Route, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const steamid64 = "76561198000000001"

const player = {
  name: "Mapper Runner",
  alias: "Mapper Alias",
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2026-03-01T12:00:00Z",
  last_played_at: "2026-03-31T12:00:00Z",
  updated_at: "2026-03-31T12:00:00Z",
  steamid64,
}

const authoredMap = {
  id: 981200,
  name: "kz_authored",
  filesize: 123456,
  validated: true,
  tiers: { OVR: 4, KZT: 4, SKZ: 2, VNL: 1 },
  bonus_count: 0,
  created_on: "2026-01-01T00:00:00Z",
  updated_on: "2026-01-02T00:00:00Z",
  approved_by_steamid64: steamid64,
  workshop_id: null,
  download_url: null,
  synced_at: "2026-03-31T00:00:00Z",
  authors: [steamid64],
  no_steamid_names: [],
  review_summary: null,
}

const otherMap = {
  ...authoredMap,
  id: 981201,
  name: "kz_other_author",
  authors: ["76561198000000002"],
}

async function installProfileMapsRoutes(
  page: Page,
  maps: (typeof authoredMap)[],
) {
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

  await page.route(/\/v1\/players\/[^/]+\/views$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ profile_views: 0 }),
    })
  })

  await page.route(/\/v1\/players\/[^/]+\/likes$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        player_likes: 0,
        viewer_likes_today: 0,
      }),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/follow-summary$/,
    async (route: Route) => {
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
    },
  )

  await page.route(
    /\/v1\/players\/[^/]+\/social-links$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
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

  await page.route(/\/v1\/maps(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(maps),
    })
  })

  await page.route(/\/v1\/maps\/wrs(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  })

  await page.route(/\/v1\/graphql$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          players: [
            {
              steamid64,
              displayName: player.alias,
              name: player.name,
              alias: player.alias,
              customId: null,
              avatarHash: null,
              country: "DE",
              primaryScope: "OVR",
              rating: 0,
              roles: [],
              lastPlayedAt: player.last_played_at,
            },
          ],
        },
      }),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/pinned-records(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
      })
    },
  )

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  })

  await page.route(/\/v1\/records\/rank(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/stats(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          steamid64,
          daily_activity: null,
          playtime: {
            updated_at: "2026-04-03T12:00:00Z",
            total_seconds: 0,
          },
        }),
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
          rank: null,
          rank_regional: null,
          region: null,
          rating: null,
          rating_easy: 0,
          rating_hard: 0,
          points: 0,
          wrs_nub: 0,
          wrs_pro: 0,
          records_900_plus: 0,
          records_800_plus: 0,
          unique_map_finishes: 0,
          player: { steamid64, display_name: player.alias },
          scope: "OVR",
        }),
      })
    },
  )
}

test("profile maps tab appears only for map authors", async ({ page }) => {
  await installProfileMapsRoutes(page, [authoredMap, otherMap])

  await page.goto(`/profile/${steamid64}`)

  await expect(page.getByRole("tab", { name: "Maps" })).toBeVisible()
  await page.getByRole("tab", { name: "Maps" }).click()
  await expect(page).toHaveURL(new RegExp(`/profile/${steamid64}/maps$`))
  await expect(page.getByTestId("map-card-kz_authored")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_other_author")).toHaveCount(0)
})

test("profile maps tab is hidden for non-authors", async ({ page }) => {
  await installProfileMapsRoutes(page, [otherMap])

  await page.goto(`/profile/${steamid64}`)

  await expect(page.getByRole("tab", { name: "Maps" })).toHaveCount(0)
})

test("direct profile maps route shows empty state for non-authors", async ({
  page,
}) => {
  await installProfileMapsRoutes(page, [otherMap])

  await page.goto(`/profile/${steamid64}/maps`)

  await expect(page.getByRole("tab", { name: "Maps" })).toHaveCount(0)
  await expect(
    page.getByText("No authored maps found for this player."),
  ).toBeVisible()
})
