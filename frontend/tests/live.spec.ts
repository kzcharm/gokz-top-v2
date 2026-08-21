import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const livePayload = {
  count: 2,
  data: [
    {
      player: {
        steamid64: "76561198000000003",
        name: "Twitch Player",
        alias: null,
        avatar_hash: null,
        country: "CA",
        custom_id: null,
        roles: null,
      },
      selected_platform: "twitch",
      selected_platform_account_identifier: "twitch-player",
      is_live: true,
      stream_url: "https://www.twitch.tv/twitch-player",
      last_viewer_count: 9123,
      preview_image_url:
        "https://static-cdn.jtvnw.net/previews-ttv/live_user_twitch-player-keyframe.jpg",
      hover_preview_image_url: null,
      stream_title: "Twitch Session",
      started_at: "2026-05-07T09:00:00Z",
      last_streamed_at: "2026-05-07T10:00:00Z",
    },
    {
      player: {
        steamid64: "76561198000000001",
        name: "Live Player",
        alias: "Live Alias",
        avatar_hash: null,
        country: "DE",
        custom_id: null,
        roles: null,
      },
      selected_platform: "bilibili",
      selected_platform_account_identifier: "123456",
      is_live: true,
      stream_url: "https://live.bilibili.com/42",
      last_viewer_count: 145612,
      preview_image_url:
        "/v1/live/preview-image?url=https%3A%2F%2Fi0.hdslb.com%2Fbfs%2Flive-key-frame%2Flive-frame.jpg",
      hover_preview_image_url: null,
      stream_title: "Live Session",
      started_at: "2026-05-07T10:00:00Z",
      last_streamed_at: "2026-05-07T10:30:00Z",
    },
  ],
}

test("Live page shows stream cards", async ({ page }) => {
  await page.route(/\/v1\/live\/streams(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(livePayload),
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
  await expect(page.getByText("Live Alias")).toBeVisible()
  await expect(page.getByText("Twitch Player")).toBeVisible()
  await expect(page.getByText("145.6K viewers")).toBeVisible()
  await expect(page.getByText("9.1K viewers")).toBeVisible()
  await expect(
    page
      .locator("article")
      .filter({ hasText: "Twitch Player" })
      .locator('[data-slot="badge"]')
      .filter({ hasText: /^Twitch$/ }),
  ).toBeVisible()
  await expect(
    page.getByText("Verified Bilibili stream link"),
  ).not.toBeVisible()
  await expect(page.getByText("Live now")).not.toBeVisible()
  await expect(
    page.getByAltText("Live Alias live keyframe preview"),
  ).toHaveAttribute(
    "src",
    /http:\/\/(?:localhost|backend):8000\/v1\/live\/preview-image\?url=.*live-key-frame/,
  )
  await expect(
    page.getByAltText("Twitch Player live keyframe preview"),
  ).toHaveAttribute(
    "src",
    "https://static-cdn.jtvnw.net/previews-ttv/live_user_twitch-player-keyframe.jpg",
  )
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
  await expect(page.getByText("No streams are live right now.")).toBeVisible()
})
