import { expect, type Route, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const accessToken = "test.eyJzdWIiOiI3NjU2MTE5ODAwMDAwMDAwMSJ9.signature"

test("notifications show unread badge and mark clicked item read", async ({
  page,
}) => {
  let unreadCount = 1
  let notificationReadAt: string | null = null

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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [
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
          count: 2,
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
  await expect(page.getByText("1 unread")).toBeVisible()
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
})
