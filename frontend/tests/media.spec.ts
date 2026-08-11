import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

test("Media page updates a visible video's view count after its deferred refresh", async ({
  page,
}) => {
  let startRefresh: (() => void) | undefined
  const refreshStarted = new Promise<void>((resolve) => {
    startRefresh = resolve
  })
  let completeRefresh: (() => void) | undefined
  const refreshCanComplete = new Promise<void>((resolve) => {
    completeRefresh = resolve
  })
  const postId = "018f01a0-0000-7000-8000-000000000001"

  await page.route(/\/v1\/media\/posts\?/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          {
            id: postId,
            player: {
              steamid64: "76561198000000001",
              display_name: "Media Player",
            },
            platform: "youtube",
            external_video_id: "video-1",
            title: "Fresh KZ run",
            url: "https://www.youtube.com/watch?v=video-1",
            published_at: "2026-08-11T10:00:00Z",
            view_count: 10,
            available: true,
          },
        ],
        next_cursor: null,
        count: 1,
      }),
    })
  })
  await page.route(/\/v1\/media\/posts\/view-counts$/, async (route) => {
    startRefresh?.()
    await refreshCanComplete
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [{ id: postId, view_count: 99 }] }),
    })
  })

  await page.goto("/media")

  await expect(page.getByText("10 views")).toBeVisible()
  await refreshStarted
  completeRefresh?.()
  await expect(page.getByText("99 views")).toBeVisible()
  await expect(page.getByText("10 views")).not.toBeVisible()
})
