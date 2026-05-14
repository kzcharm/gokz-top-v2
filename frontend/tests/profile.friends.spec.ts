import { expect, type Page, test } from "@playwright/test"

const steamid64 = "76561198000000001"
const friendSteamid64 = "76561198000000002"

const player = {
  name: "Owner",
  alias: "Owner Alias",
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2026-03-01T12:00:00Z",
  last_played_at: "2026-03-31T12:00:00Z",
  updated_at: "2026-03-31T12:00:00Z",
  steamid64,
  profile_views: 0,
}

const friend = {
  name: "Friend",
  alias: "Friend Alias",
  custom_id: null,
  avatar_hash: null,
  country: "SE",
  created_at: "2026-03-02T12:00:00Z",
  last_played_at: "2026-03-30T12:00:00Z",
  updated_at: "2026-03-30T12:00:00Z",
  steamid64: friendSteamid64,
  profile_views: 0,
}

async function installProfileShellRoutes(
  page: Page,
  {
    currentUserSteamid64,
    friendsPayload,
    onSync,
  }: {
    currentUserSteamid64: string | null
    friendsPayload: () => object
    onSync?: () => object
  },
) {
  if (currentUserSteamid64) {
    await page.route(/\/v1\/users\/me$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          steamid64: currentUserSteamid64,
          is_active: true,
          roles: [],
        }),
      })
    })
  } else {
    await page.route(/\/v1\/users\/me$/, async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Unauthorized" }),
      })
    })
  }

  await page.route(/\/v1\/players\/[^/]+$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(player),
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
        viewer_is_self: currentUserSteamid64 === steamid64,
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

  await page.route(/\/v1\/players\/[^/]+\/friends$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(friendsPayload()),
    })
  })

  await page.route(/\/v1\/players\/[^/]+\/friends\/sync$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(onSync ? onSync() : friendsPayload()),
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

  await page.route(
    /\/v1\/leaderboards\/players\/[^/?]+(\?.*)?$/,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rank: null,
          rank_regional: null,
          region: null,
          rating: null,
        }),
      })
    },
  )
}

test("Own friends tab auto-syncs once and supports manual sync", async ({
  page,
}) => {
  let getFriendsCalls = 0
  let syncCalls = 0

  await installProfileShellRoutes(page, {
    currentUserSteamid64: steamid64,
    friendsPayload: () => {
      getFriendsCalls += 1
      return getFriendsCalls === 1
        ? {
            data: [],
            count: 0,
            sync: {
              visibility: null,
              last_checked_at: null,
              last_attempted_at: null,
              next_allowed_at: null,
            },
          }
        : {
            data: [friend],
            count: 1,
            sync: {
              visibility: "public",
              last_checked_at: "2026-05-13T12:00:00Z",
              last_attempted_at: "2026-05-13T12:00:00Z",
              next_allowed_at: null,
            },
          }
    },
    onSync: () => {
      syncCalls += 1
      return {
        data: [friend],
        count: 1,
        sync: {
          visibility: "public",
          last_checked_at: "2026-05-13T12:00:00Z",
          last_attempted_at: "2026-05-13T12:00:00Z",
          next_allowed_at: null,
        },
      }
    },
  })

  await page.goto(`/profile/${steamid64}/friends`)

  await expect(page.getByRole("tab", { name: "Friends" })).toHaveAttribute(
    "data-state",
    "active",
  )
  await expect(page.getByTestId("profile-friends-list")).toBeVisible()
  await expect(page.getByText("Friend Alias")).toBeVisible()
  await expect.poll(() => syncCalls).toBe(1)

  await page.getByTestId("profile-friends-sync-button").click()
  await expect.poll(() => syncCalls).toBe(2)
})

test("Public visitor sees privacy warning and no sync button", async ({
  page,
}) => {
  await installProfileShellRoutes(page, {
    currentUserSteamid64: null,
    friendsPayload: () => ({
      data: [],
      count: 0,
      sync: {
        visibility: "private_friends",
        last_checked_at: "2026-05-13T12:00:00Z",
        last_attempted_at: "2026-05-13T12:00:00Z",
        next_allowed_at: null,
      },
    }),
  })

  await page.goto(`/profile/${steamid64}/friends`)

  await expect(page.getByTestId("profile-friends-warning")).toBeVisible()
  await expect(page.getByTestId("profile-friends-sync-button")).toHaveCount(0)
})
