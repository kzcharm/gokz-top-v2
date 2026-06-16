import { expect, type Route, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const accessToken = "test.eyJzdWIiOiI3NjU2MTE5ODAwMDAwMDAwMSJ9.signature"

test("notifications show unread badge and mark clicked item read", async ({
  page,
}) => {
  let unreadCount = 1
  let notificationReadAt: string | null = null
  const notificationRequests: Array<{
    offset: string | null
    limit: string | null
  }> = []

  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, accessToken)

  await page.route(/\/v1\/users\/me$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        steamid64: "76561198000000001",
        is_active: true,
        roles: [],
      }),
    })
  })

  await page.route(/\/v1\/admin\/servers\/access$/, async (route: Route) => {
    await route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Forbidden" }),
    })
  })

  await page.route(/\/v1\/live\/streams(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })

  await page.route(/\/v1\/graphql$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: {} }),
    })
  })

  await page.route(
    /\/v1\/me\/notifications\/unread-count$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ unread_count: unreadCount }),
      })
    },
  )

  await page.route(
    /\/v1\/me\/notifications(?:\?.*)?$/,
    async (route: Route) => {
      const url = new URL(route.request().url())
      const offset = url.searchParams.get("offset")
      const limit = url.searchParams.get("limit")
      notificationRequests.push({ offset, limit })
      const isSecondPage = offset === "20"

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: isSecondPage
            ? [
                {
                  id: "019b82f7-0f30-7000-8000-000000000003",
                  type: "player_follow",
                  created_at: "2026-06-03T06:00:00Z",
                  read_at: "2026-06-03T06:05:00Z",
                  actor: {
                    steamid64: "76561198000000004",
                    display_name: "Page Two Runner",
                  },
                  target_url: "/profile/76561198000000004",
                  target_player_steamid64: "76561198000000004",
                },
              ]
            : [
                {
                  id: "019b82f7-0f30-7000-8000-000000000001",
                  type: "profile_like",
                  created_at: "2026-06-03T08:00:00Z",
                  read_at: notificationReadAt,
                  actor: {
                    steamid64: "76561198000000002",
                    display_name: "Like Runner",
                  },
                  target_url: "/notifications?opened=1",
                  target_player_steamid64: "76561198000000002",
                },
                {
                  id: "019b82f7-0f30-7000-8000-000000000002",
                  type: "wr_beaten",
                  created_at: "2026-06-03T07:00:00Z",
                  read_at: "2026-06-03T07:05:00Z",
                  actor: {
                    steamid64: "76561198000000003",
                    display_name: "WR Runner",
                  },
                  target_url: "/maps/kz_wr/maptop?scope=KZT&type=PRO",
                  map_id: 123,
                  map_name: "kz_wr",
                  scope: "KZT",
                  record_type: "PRO",
                  new_record_time: 9.876,
                },
              ],
          count: 21,
        }),
      })
    },
  )

  await page.route(
    /\/v1\/me\/notifications\/[^/]+\/read$/,
    async (route: Route) => {
      unreadCount = 0
      notificationReadAt = "2026-06-03T08:01:00Z"
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "019b82f7-0f30-7000-8000-000000000001",
          type: "profile_like",
          created_at: "2026-06-03T08:00:00Z",
          read_at: notificationReadAt,
          actor: {
            steamid64: "76561198000000002",
            display_name: "Like Runner",
          },
          target_url: "/notifications?opened=1",
          target_player_steamid64: "76561198000000002",
        }),
      })
    },
  )

  await page.goto("/notifications")

  await expect(
    page.getByRole("heading", { name: "Notifications" }),
  ).toBeVisible()
  await expect.poll(() => notificationRequests.length).toBeGreaterThan(0)
  expect(notificationRequests[0]).toEqual({ offset: "0", limit: "20" })
  await expect(page.getByText("(1 unread)")).toBeVisible()
  await expect(page.getByText("Total 21 Notifications")).toBeVisible()
  await expect(page.getByText("Like Runner")).toBeVisible()
  await expect(page.getByText("liked your profile.")).toBeVisible()
  await expect(page.getByText("WR Runner")).toBeVisible()
  await expect(page.getByText("beat your WR on")).toBeVisible()
  await expect(page.getByRole("link", { name: "kz_wr" })).toHaveAttribute(
    "href",
    "/maps/kz_wr/maptop?scope=KZT&type=PRO",
  )
  await expect(
    page
      .locator('a[href="/profile/76561198000000002"]')
      .filter({ hasText: "Like Runner" }),
  ).toBeVisible()
  await expect(page.getByText("Unread", { exact: true })).toBeVisible()

  await page.getByText("liked your profile.").click()

  await expect(page).toHaveURL(/\/notifications$/)
  await expect(page.getByText("0 unread")).toBeVisible()

  await Promise.all([
    page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        url.pathname === "/v1/me/notifications" &&
        url.searchParams.get("offset") === "20" &&
        url.searchParams.get("limit") === "20"
      )
    }),
    page.getByRole("button", { name: "Go to next page" }).click(),
  ])

  await expect(page.getByText("Page Two Runner")).toBeVisible()
  expect(notificationRequests).toContainEqual({ offset: "20", limit: "20" })
})

test("notifications show deleted map review comment text and map link", async ({
  page,
}) => {
  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, accessToken)

  await page.route(/\/v1\/users\/me$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        steamid64: "76561198000000001",
        is_active: true,
        roles: [],
      }),
    })
  })

  await page.route(/\/v1\/admin\/servers\/access$/, async (route: Route) => {
    await route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Forbidden" }),
    })
  })

  await page.route(/\/v1\/live\/streams(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })

  await page.route(/\/v1\/graphql$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: {} }),
    })
  })

  await page.route(
    /\/v1\/me\/notifications\/unread-count$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ unread_count: 1 }),
      })
    },
  )

  await page.route(
    /\/v1\/me\/notifications(?:\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [
            {
              id: "019b82f7-0f30-7000-8000-000000000010",
              type: "map_review_comment_deleted",
              created_at: "2026-06-03T08:00:00Z",
              read_at: null,
              actor: null,
              target_url: "/maps/kz_alpha/reviews",
              target_player_steamid64: "76561198000000001",
              comment_preview: "original comment",
              comment_text: "original comment\nwith second line",
              map_id: 980200,
              map_name: "kz_alpha",
            },
          ],
          count: 1,
        }),
      })
    },
  )

  await page.goto("/notifications")

  await expect(page.getByText("Review Admin")).toHaveCount(0)
  await expect(page.getByText("Your map review comment on")).toBeVisible()
  await expect(page.getByRole("link", { name: "kz_alpha" })).toHaveAttribute(
    "href",
    "/maps/kz_alpha/reviews",
  )
  await expect(page.getByText("original comment")).toBeVisible()
  await expect(page.getByText("with second line")).toBeVisible()
})
