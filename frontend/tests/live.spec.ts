import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const livePayload = {
  count: 1,
  data: [
    {
      player: {
        steamid64: "76561198000000001",
        name: "Live Player",
        alias: "Live Alias",
        avatar_hash: null,
        country: "DE",
        custom_id: null,
        is_website_user: false,
      },
      selected_platform: "bilibili",
      selected_platform_account_identifier: "123456",
      is_live: true,
      stream_url: "https://live.bilibili.com/42",
      last_viewer_count: 145612,
      preview_image_url:
        "/v1/live/preview-image?url=https%3A%2F%2Fi0.hdslb.com%2Fbfs%2Flive%2Flive-cover.jpg",
      stream_title: "Live Session",
      started_at: "2026-05-07T10:00:00Z",
      last_streamed_at: "2026-05-07T10:30:00Z",
    },
  ],
}

const offlinePayload = {
  count: 1,
  data: [
    {
      player: {
        steamid64: "76561198000000002",
        name: "Offline Player",
        alias: null,
        avatar_hash: null,
        country: "US",
        custom_id: null,
        is_website_user: false,
      },
      selected_platform: "bilibili",
      selected_platform_account_identifier: "654321",
      is_live: false,
      stream_url: "https://live.bilibili.com/84",
      last_viewer_count: 4012,
      preview_image_url: null,
      stream_title: "Last Session",
      started_at: null,
      last_streamed_at: "2026-05-06T10:30:00Z",
    },
  ],
}

test("Live page switches between live and offline streams", async ({
  page,
}) => {
  await page.route(/\/v1\/live\/streams(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const online = url.searchParams.get("online")
    const payload = online === "false" ? offlinePayload : livePayload

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    })
  })

  await page.route(/\/v1\/live\/preview-image(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/jpeg",
      body: "preview-image",
    })
  })

  await page.goto("/live")

  await expect(page.getByRole("heading", { name: "Live" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Online" })).toBeVisible()
  await expect(page.getByText("Live Alias")).toBeVisible()
  await expect(page.getByText("145.6K views")).toBeVisible()
  await expect(
    page.getByText("Verified Bilibili stream link"),
  ).not.toBeVisible()
  await expect(page.getByText("Live now")).not.toBeVisible()
  await expect(page.getByAltText("Live Alias stream preview")).toHaveAttribute(
    "src",
    /http:\/\/localhost:8000\/v1\/live\/preview-image\?/,
  )

  await page.getByRole("button", { name: "Online" }).click()
  await expect(page.getByText("Offline Player")).toBeVisible()
  await expect(page.getByText("4K views")).toBeVisible()
  await expect(page.getByText("Live Alias")).not.toBeVisible()

  await page.getByRole("button", { name: "Online" }).click()
  await expect(page.getByText("Live Alias")).toBeVisible()
  await expect(page.getByText("Offline Player")).not.toBeVisible()
})

test("Live page shows the empty state when no streams are tracked", async ({
  page,
}) => {
  await page.route(/\/v1\/live\/streams(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })

  await page.goto("/live")

  await expect(page.getByText("Nothing to show")).toBeVisible()
  await expect(
    page.getByText("No verified Bilibili streams are live right now."),
  ).toBeVisible()
})
