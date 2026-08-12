import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

test("Media notification dot only returns for videos published after a visit", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.removeItem("gokz-media-last-visited-at")
  })
  await page.route(/\/v1\/live\/streams(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })
  let mediaRequestCount = 0
  await page.route(/\/v1\/media\/posts\?/, async (route) => {
    mediaRequestCount += 1
    const publishedAt =
      mediaRequestCount >= 3 ? "2099-01-01T00:00:00Z" : "2020-01-01T00:00:00Z"
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          {
            id: "018f01a0-0000-7000-8000-000000000004",
            player: {
              steamid64: "76561198000000004",
              display_name: "Media Player",
            },
            platform: "youtube",
            external_video_id: "media-video",
            title: "Media video",
            url: "https://www.youtube.com/watch?v=media-video",
            published_at: publishedAt,
            view_count: 1,
            available: true,
          },
        ],
        next_cursor: null,
        count: 1,
      }),
    })
  })
  await page.route(/\/v1\/media\/posts\/view-counts$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [] }),
    })
  })

  await page.goto("/servers")

  const mediaLink = page.getByRole("link", { name: "Media" })
  await expect(
    mediaLink.locator('span[aria-hidden="true"].bg-red-500'),
  ).toBeVisible()

  await mediaLink.click()
  await expect(page).toHaveURL(/\/media$/)

  await page.getByRole("link", { name: "Servers" }).click()
  await expect(
    page
      .getByRole("link", { name: "Media" })
      .locator('span[aria-hidden="true"].bg-red-500'),
  ).toHaveCount(0)

  await page.reload()
  await expect(
    page
      .getByRole("link", { name: "Media" })
      .locator('span[aria-hidden="true"].bg-red-500'),
  ).toBeVisible()
})

test("Media page filters videos by one platform and toggles the selection", async ({
  page,
}) => {
  await page.route(/\/v1\/media\/posts\?/, async (route) => {
    const requestUrl = new URL(route.request().url())
    const platform = requestUrl.searchParams.get("platform")
    const sort = requestUrl.searchParams.get("sort")
    const youtubePost = {
      id: "018f01a0-0000-7000-8000-000000000002",
      player: {
        steamid64: "76561198000000002",
        display_name: "YouTube Player",
      },
      platform: "youtube",
      external_video_id: "youtube-video",
      title: "YouTube KZ run",
      url: "https://www.youtube.com/watch?v=youtube-video",
      published_at: "2026-08-11T10:00:00Z",
      view_count: 10,
      duration_seconds: 60,
      available: true,
    }
    const bilibiliPost = {
      id: "018f01a0-0000-7000-8000-000000000003",
      player: {
        steamid64: "76561198000000003",
        display_name: "Bilibili Player",
      },
      platform: "bilibili",
      external_video_id: "bilibili-video",
      title: "Bilibili KZ run",
      url: "https://www.bilibili.com/video/bilibili-video",
      published_at: "2026-08-11T10:00:00Z",
      view_count: 20,
      duration_seconds: 120,
      available: true,
    }
    const posts = [youtubePost, bilibiliPost]
      .filter((post) => platform === null || post.platform === platform)
      .toSorted((left, right) =>
        sort === "latest"
          ? right.published_at.localeCompare(left.published_at)
          : sort === "views"
            ? right.view_count - left.view_count
            : (right.duration_seconds ?? -1) - (left.duration_seconds ?? -1),
      )
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: posts,
        next_cursor: null,
        count: posts.length,
      }),
    })
  })
  await page.route(/\/v1\/media\/posts\/view-counts$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [] }),
    })
  })

  await page.goto("/media")

  await expect(page.getByText("YouTube KZ run")).toBeVisible()
  await expect(page.getByText("Bilibili KZ run")).toBeVisible()

  await page.getByRole("button", { name: "YouTube" }).click()
  await expect(page.getByText("YouTube KZ run")).toBeVisible()
  await expect(page.getByText("Bilibili KZ run")).not.toBeVisible()
  await expect(page.getByRole("button", { name: "YouTube" })).toHaveAttribute(
    "aria-pressed",
    "true",
  )
  await expect(page.getByRole("button", { name: "YouTube" })).toHaveClass(
    /bg-red-600/,
  )

  await page.getByRole("button", { name: "Bilibili" }).click()
  await expect(page.getByText("YouTube KZ run")).not.toBeVisible()
  await expect(page.getByText("Bilibili KZ run")).toBeVisible()
  await expect(page.getByRole("button", { name: "Bilibili" })).toHaveClass(
    /bg-pink-500/,
  )

  await page.getByRole("button", { name: "Bilibili" }).click()
  await expect(page.getByText("YouTube KZ run")).toBeVisible()
  await expect(page.getByText("Bilibili KZ run")).toBeVisible()

  await page.getByRole("combobox", { name: "Sort media" }).click()
  await page.getByRole("option", { name: "Most views" }).click()
  await expect(page.locator("article").first()).toContainText("Bilibili KZ run")

  await page.getByRole("combobox", { name: "Sort media" }).click()
  await page.getByRole("option", { name: "Video length" }).click()
  await expect(page.locator("article").first()).toContainText("Bilibili KZ run")
})

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

test("Media page loads the next page when the load-more control enters view", async ({
  page,
}) => {
  const firstPagePosts = Array.from({ length: 24 }, (_, index) => ({
    id: `018f01a0-0000-7000-8000-${String(index).padStart(12, "0")}`,
    player: {
      steamid64: "76561198000000001",
      display_name: "Media Player",
    },
    platform: "youtube",
    external_video_id: `video-${index}`,
    title: `Media video ${index + 1}`,
    url: `https://www.youtube.com/watch?v=video-${index}`,
    published_at: "2026-08-11T10:00:00Z",
    view_count: index,
    available: true,
  }))

  await page.route(/\/v1\/media\/posts\?/, async (route) => {
    const cursor = new URL(route.request().url()).searchParams.get("cursor")
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        cursor
          ? {
              data: [
                {
                  ...firstPagePosts[0],
                  id: "018f01a0-0000-7000-8000-000000000024",
                  title: "Media video 25",
                },
              ],
              next_cursor: null,
              count: 1,
            }
          : {
              data: firstPagePosts,
              next_cursor: "next-page",
              count: 25,
            },
      ),
    })
  })
  await page.route(/\/v1\/media\/posts\/view-counts$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [] }),
    })
  })

  await page.goto("/media")
  await page.getByRole("button", { name: "Load more" }).scrollIntoViewIfNeeded()

  await expect(page.getByText("Media video 25")).toBeVisible()
})
