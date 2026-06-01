import { expect, type Page, type Route, test } from "@playwright/test"

test.use({
  baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173",
  storageState: { cookies: [], origins: [] },
})

const viewedPlayer = {
  steamid64: "76561198000001001",
  displayName: "View Hero",
  name: "View Hero",
  alias: null,
  customId: null,
  avatarHash: null,
  country: "DE",
  primaryScope: "OVR",
  rating: 5.21,
  roles: [],
  lastPlayedAt: "2026-05-01T12:00:00Z",
}

const likedPlayer = {
  steamid64: "76561198000001002",
  displayName: "Like Hero",
  name: "Like Hero",
  alias: null,
  customId: null,
  avatarHash: null,
  country: "US",
  primaryScope: "OVR",
  rating: 4.72,
  roles: [],
  lastPlayedAt: "2026-05-02T12:00:00Z",
}

async function installCommonRoutes(page: Page) {
  await page.route(/\/v1\/users\/me$/, async (route: Route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Unauthorized" }),
    })
  })

  await page.route(/\/v1\/live\/streams(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })

  await page.route(/\/v1\/graphql$/, async (route: Route) => {
    const requestBody = route.request().postDataJSON() as {
      variables?: { steamid64s?: string[] }
    }
    const steamid64s = requestBody.variables?.steamid64s ?? []
    const players = steamid64s.map((steamid64) => {
      if (steamid64 === likedPlayer.steamid64) {
        return likedPlayer
      }
      if (steamid64 === viewedPlayer.steamid64) {
        return viewedPlayer
      }
      const index = Number.parseInt(steamid64.slice(-3), 10) + 1
      const displayName = `Community Player ${index}`
      return {
        ...viewedPlayer,
        steamid64,
        displayName,
        name: displayName,
      }
    })
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: { players } }),
    })
  })
}

test("Community leaderboard sorts by selected community field", async ({
  page,
}) => {
  await installCommonRoutes(page)
  await page.route(
    /\/v1\/leaderboards\/community(\?.*)?$/,
    async (route: Route) => {
      const url = new URL(route.request().url())
      const sortBy = url.searchParams.get("sort_by")
      const row =
        sortBy === "platform_followers"
          ? {
              rank: 1,
              player: {
                steamid64: likedPlayer.steamid64,
                display_name: likedPlayer.displayName,
              },
              views_count: 5,
              unique_visitors: 3,
              likes: 77,
              unique_likers: 25,
              video_platform_followers: {
                platform: "bilibili",
                followers_count: 987654,
                url: "https://space.bilibili.com/123456",
                updated_at: "2026-05-01T12:00:00Z",
              },
            }
          : sortBy === "likes"
            ? {
                rank: 1,
                player: {
                  steamid64: likedPlayer.steamid64,
                  display_name: likedPlayer.displayName,
                },
                views_count: 5,
                unique_visitors: 3,
                likes: 77,
                unique_likers: 25,
                video_platform_followers: {
                  platform: "bilibili",
                  followers_count: 54321,
                  url: "https://space.bilibili.com/123456",
                  updated_at: "2026-05-01T12:00:00Z",
                },
              }
            : {
                rank: 1,
                player: {
                  steamid64: viewedPlayer.steamid64,
                  display_name: viewedPlayer.displayName,
                },
                views_count: 1234,
                unique_visitors: 321,
                likes: 12,
                unique_likers: 8,
                video_platform_followers: {
                  platform: "youtube",
                  followers_count: 123456,
                  url: "https://www.youtube.com/@viewhero",
                  updated_at: "2026-05-01T12:00:00Z",
                },
              }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: [row], count: 1 }),
      })
    },
  )

  await page.goto("/leaderboards/community")

  await expect(page.getByRole("tab", { name: "Community" })).toHaveAttribute(
    "aria-selected",
    "true",
  )
  await expect(page.getByText("Community Rankings")).toBeVisible()
  await expect(page.getByRole("button", { name: /Views Count/ })).toBeVisible()
  await expect(
    page.getByRole("button", { name: /Platform Followers/ }),
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: /Unique Visitors/ }),
  ).toBeVisible()
  await expect(page.getByRole("button", { name: /Likes/ })).toBeVisible()
  await expect(
    page.getByRole("button", { name: /Unique Likers/ }),
  ).toBeVisible()
  await expect(page.getByText("View Hero")).toBeVisible()
  await expect(page.getByText("1,234", { exact: true })).toBeVisible()
  await expect(page.getByText("321", { exact: true })).toBeVisible()
  await expect(page.getByText("123,456", { exact: true })).toBeVisible()
  await expect(
    page.getByRole("link", { name: "Open YouTube profile" }),
  ).toHaveAttribute("href", "https://www.youtube.com/@viewhero")

  await page.getByRole("button", { name: /Platform Followers/ }).click()

  await expect(page.getByText("Like Hero")).toBeVisible()
  await expect(page.getByText("987,654", { exact: true })).toBeVisible()
  await expect(
    page.getByRole("link", { name: "Open Bilibili profile" }),
  ).toHaveAttribute("href", "https://space.bilibili.com/123456")

  await page.getByRole("button", { name: /Likes/ }).click()

  await expect(page.getByText("Like Hero")).toBeVisible()
  await expect(page.getByText("77", { exact: true })).toBeVisible()
  await expect(page.getByText("25", { exact: true })).toBeVisible()
  await expect(page.getByText("54,321", { exact: true })).toBeVisible()
})

test("Community leaderboard shows more than ten rows", async ({ page }) => {
  await installCommonRoutes(page)
  await page.route(
    /\/v1\/leaderboards\/community(\?.*)?$/,
    async (route: Route) => {
      const url = new URL(route.request().url())
      expect(url.searchParams.get("limit")).toBe("100")

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: Array.from({ length: 11 }, (_value, index) => ({
            rank: index + 1,
            player: {
              steamid64: `76561198000002${String(index).padStart(3, "0")}`,
              display_name: `Community Player ${index + 1}`,
            },
            views_count: 100 - index,
            unique_visitors: 50 - index,
            likes: 25 - index,
            unique_likers: 10 - index,
            video_platform_followers: null,
          })),
          count: -1,
        }),
      })
    },
  )

  await page.goto("/leaderboards/community")

  await expect(
    page.getByText("Community Player 11", { exact: true }),
  ).toBeVisible()
  await expect(page.getByRole("cell", { name: "-", exact: true })).toHaveCount(
    11,
  )
  await expect(page.getByText("Rows per page")).toHaveCount(0)
})

test("Community leaderboard shows empty state", async ({ page }) => {
  await installCommonRoutes(page)
  await page.route(
    /\/v1\/leaderboards\/community(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
      })
    },
  )

  await page.goto("/leaderboards/community")

  await expect(
    page.getByText("No community ranking entries found."),
  ).toBeVisible()
})

test("Community leaderboard shows API errors", async ({ page }) => {
  await installCommonRoutes(page)
  await page.route(
    /\/v1\/leaderboards\/community(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Community rankings unavailable" }),
      })
    },
  )

  await page.goto("/leaderboards/community")

  await expect(page.getByText("Unable to load community rankings")).toBeVisible(
    { timeout: 15_000 },
  )
})
